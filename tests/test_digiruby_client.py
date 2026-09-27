"""Currency selection and review-first exchange stay server authoritative."""
import copy
import os
import queue
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
import pygame

from tools.preview_ui_screens import ROOT,game_fixture,make_app
from venom.client.display import effective_ui_scale
from venom.client.render import NativeCanvas
from venom.common.economy import MAX_CREDITS
from venom.common.game import SHOP
import test_community_client as community_harness


class Connection:
    connected=True
    def __init__(self):
        self.sent=[]
        self.incoming=queue.Queue()
    def send(self,operation,**payload):
        self.sent.append((operation,payload))
        return len(self.sent)


@unittest.skipUnless((ROOT/'data/catalog.json').exists(),'Imported assets required')
class DigiRubyClientTests(unittest.TestCase):
    def setUp(self):
        self.app=make_app('1280x800')
        self.addCleanup(pygame.quit)
        self.app.state=game_fixture(self.app)
        self.app.state.update(in_farm=True,in_lab=False,in_story=False,in_season=False,battle=None,
            credits=100000,digirubies=2400,
            economy=dict(enabled=True,credits_per_ruby=100,max_exchange_rubies=100000,max_credits=MAX_CREDITS))
        self.app.args.demo=False
        self.app.server_features={'digiruby_economy'}
        self.app.connection=Connection()
        self.app.community.data=community_harness.fixture(self.app)
        self.app.menu='shop'
        self.controls=[]
        for owner in (self.app.ui,self.app.community):
            original=owner.button
            def capture(rect,label,callback,*args,_original=original,**kwargs):
                self.controls.append((label,pygame.Rect(rect),kwargs))
                return _original(rect,label,callback,*args,**kwargs)
            self.enterContext(patch.object(owner,'button',side_effect=capture))

    def draw(self):
        self.controls.clear()
        self.app.draw()

    def click(self,label,prefix=False):
        area=next(rect for name,rect,options in self.controls
                  if (name.startswith(label) if prefix else name==label) and not options.get('disabled'))
        self.app.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,
                                           pos=self.app.screen.to_physical_point(area.center)))

    def exchange(self):
        self.app.menu='community'
        self.app.community.tab,self.app.community.mode='ranked','exchange'
        self.app.community.set_exchange_amount(10)
        self.draw()

    def reply(self,ok=True,**fields):
        self.app.connection.incoming.put(dict(op='result',rid=len(self.app.connection.sent),ok=ok,**fields))
        self.app.poll()

    def test_ruby_checkout_uses_quoted_currency_and_quantity_without_local_grants(self):
        self.draw();self.click('DigiRubies ·',True)
        self.app.shop_screen.quantities['hp_s']=3
        self.draw()
        before=copy.deepcopy(self.app.state)
        self.click('Buy')
        operation,payload=self.app.connection.sent[-1]
        self.assertEqual(operation,'shop')
        self.assertEqual((payload['item'],payload['quantity'],payload['currency']),('hp_s',3,'digirubies'))
        self.assertEqual(len(payload['transaction_id']),32)
        self.assertEqual(self.app.state,before)
        self.assertTrue(self.app.action_pending)
        self.app.shop_screen.buy('hp_s')
        self.assertEqual(len(self.app.connection.sent),1)
        after=copy.deepcopy(before);after['digirubies']-=3*before['shop']['hp_s']['ruby_price']
        after['inventory']['hp_s']=after['inventory'].get('hp_s',0)+3
        self.reply(state=after)
        self.assertFalse(self.app.action_pending)
        self.assertEqual(self.app.state['digirubies'],after['digirubies'])

    def test_all_regular_items_have_ruby_quotes_and_currency_specific_affordability(self):
        self.app.shop_screen.select_currency('digirubies')
        self.app.state['credits']=0
        for key,item in self.app.state['shop'].items():
            self.assertEqual(self.app.shop_screen.unit_price(item),item['ruby_price'])
            self.assertTrue(self.app.shop_screen.can_buy(key,item,1),key)
        self.app.state['digirubies']=0
        self.assertFalse(self.app.shop_screen.can_buy('hp_s',self.app.state['shop']['hp_s'],1))
        self.app.shop_screen.select_currency('credits')
        self.assertFalse(self.app.shop_screen.can_buy('hp_s',self.app.state['shop']['hp_s'],1))
        self.app.state['credits']=1000
        self.assertTrue(self.app.shop_screen.can_buy('hp_s',self.app.state['shop']['hp_s'],1))

    def test_old_server_fails_closed_for_rubies_but_credits_still_work(self):
        self.app.server_features=set()
        self.app.shop_screen.select_currency('digirubies')
        self.assertEqual(self.app.shop_screen.currency,'credits')
        self.app.shop_screen.buy('hp_s')
        self.assertEqual(self.app.connection.sent[-1],('shop',dict(item='hp_s',quantity=1)))
        self.app.action_pending=False
        self.exchange();self.app.community.review_exchange()
        self.assertIsNone(self.app.community.exchange_review)
        self.assertIn('updated server',self.app.community.error)

    def test_exchange_reviews_before_spending_and_only_matching_receipt_finishes(self):
        self.exchange();before=copy.deepcopy(self.app.state)
        self.click('Review exchange')
        self.assertFalse(self.app.connection.sent)
        self.draw();self.assertEqual(len(self.app.ui.actions),2)
        self.click('Confirm exchange')
        self.assertEqual(self.app.state,before)
        operation,payload=self.app.connection.sent[-1]
        self.assertEqual((operation,payload['action'],payload['amount']),('community','exchange',10))
        self.app.community.confirm_exchange()
        self.app.community.cancel_exchange_review()
        self.assertEqual(len(self.app.connection.sent),1)
        self.assertTrue(self.app.community.exchange_modal)
        self.app.community.receive(dict(action='exchange',data={}),rid=999)
        self.assertIn('exchange',self.app.community.pending)
        after=copy.deepcopy(before);after['digirubies']-=10;after['credits']+=1000
        self.reply(state=after,community=dict(action='exchange',data=dict(rubies_spent=10,credits_gained=1000,balance=2390,duplicate=False)))
        self.assertFalse(self.app.community.pending)
        self.assertFalse(self.app.community.exchange_modal)
        self.assertEqual(self.app.state['credits'],101000)
        self.assertEqual(self.app.community.exchange_receipt['credits_gained'],1000)

    def test_failed_exchange_can_retry_the_same_idempotent_request(self):
        self.exchange();self.click('Review exchange');self.app.community.confirm_exchange()
        original=self.app.connection.sent[-1][1]
        self.reply(ok=False,error='Database is temporarily unavailable.')
        self.assertFalse(self.app.community.pending)
        self.assertTrue(self.app.community.exchange_modal)
        self.assertIn('temporarily',self.app.community.error)
        self.app.community.confirm_exchange()
        self.assertEqual(self.app.connection.sent[-1][1],original)

    def test_review_keyboard_cannot_trigger_gameplay_or_accidental_confirm(self):
        self.exchange();self.click('Review exchange')
        for key in (pygame.K_F2,pygame.K_p,pygame.K_RETURN):
            self.app.key(pygame.event.Event(pygame.KEYDOWN,key=key))
        self.assertFalse(self.app.connection.sent)
        self.assertEqual(self.app.menu,'community')
        self.assertTrue(self.app.community.exchange_modal)
        self.app.key(pygame.event.Event(pygame.KEYDOWN,key=pygame.K_ESCAPE))
        self.assertFalse(self.app.community.exchange_modal)
        self.assertEqual(self.app.menu,'community')

    def test_amount_validation_and_max_respect_wallet_server_limit_and_credit_capacity(self):
        self.exchange()
        for value in ('','0','-1','1.5','1e2','１２','100001','99999999999999999999'):
            self.app.ui.values['ruby_exchange_amount']=value
            self.assertTrue(self.app.community.exchange_problem(),value)
        self.app.state['digirubies']=200000
        self.assertEqual(self.app.community.exchange_maximum(),100000)
        self.app.state['credits']=MAX_CREDITS-299
        self.assertEqual(self.app.community.exchange_maximum(),2)
        self.app.community.set_exchange_amount(3)
        self.assertIn('near their limit',self.app.community.exchange_problem())
        self.app.state['credits']=MAX_CREDITS
        self.assertEqual(self.app.community.exchange_maximum(),0)

    def test_shop_exchange_and_review_controls_fit_small_and_native_displays(self):
        for size in ((960,540),(1180,800),(1920,1080)):
            self.app.screen=NativeCanvas(pygame.display.set_mode(size),effective_ui_scale(size,'auto'))
            self.app.ui.screen=self.app.screen
            for mode in ('shop','exchange','review'):
                self.app.community.exchange_review=None
                if mode=='shop':
                    self.app.menu='shop';self.app.shop_screen.select_currency('digirubies')
                else:
                    self.exchange()
                    if mode=='review':self.app.community.review_exchange()
                self.draw()
                for label,rect,_ in self.controls:
                    self.assertTrue(self.app.screen.get_rect().contains(rect),(size,mode,label,rect))


if __name__=='__main__':unittest.main()
