# Windows PowerShell 5.1. Run normally; the official installer requests UAC.
$ErrorActionPreference = 'Stop'
$downloadDirectory = $null
$exitCode = 1
try {
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'This server bundle requires 64-bit Windows.'
    }
    Write-Host 'Downloading the Microsoft Visual C++ v14 x64 runtime from Microsoft...'
    Write-Host 'The Microsoft installer will open after its digital signature is verified.'
    $downloadDirectory = Join-Path ([IO.Path]::GetTempPath()) ('DigimonVenomNXT-VC-' + [Guid]::NewGuid().ToString('N'))
    [void][IO.Directory]::CreateDirectory($downloadDirectory)
    $installer = Join-Path $downloadDirectory 'VC_redist.x64.exe'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $response = Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vc14/vc_redist.x64.exe' -OutFile $installer -PassThru -TimeoutSec 180
    $finalUri = $response.BaseResponse.ResponseUri
    if ($null -eq $finalUri -or $finalUri.Scheme -ne 'https' -or
        ($finalUri.Host -ne 'aka.ms' -and $finalUri.Host -notlike '*.microsoft.com')) {
        throw 'The download did not finish at an official Microsoft HTTPS address.'
    }
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
        throw 'Microsoft runtime download did not produce an installer.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
        $null -eq $signature.SignerCertificate) {
        throw ('The Microsoft installer signature could not be verified: ' + $signature.Status)
    }
    $publisher = $signature.SignerCertificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
    if ($publisher -ne 'Microsoft Corporation') {
        throw ('Unexpected installer publisher: ' + $publisher)
    }
    Write-Host 'Verified publisher: Microsoft Corporation.'
    Write-Host 'Follow the official installer. Windows may ask for administrator permission.'
    $process = Start-Process -FilePath $installer -ArgumentList @('/install', '/norestart') -Verb RunAs -Wait -PassThru
    $exitCode = $process.ExitCode
    switch ($exitCode) {
        0 { Write-Host 'Microsoft Visual C++ runtime setup completed.' }
        3010 { Write-Host 'Runtime setup completed. Restart Windows to finish.' }
        default { throw ('Microsoft runtime installer returned exit code ' + $exitCode + '. Setup was not confirmed successful.') }
    }
}
catch {
    Write-Host ''
    Write-Host ('Runtime setup stopped: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'You can also download and run the x64 package directly from:'
    Write-Host 'https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist'
    if ($exitCode -eq 0 -or $exitCode -eq 3010) { $exitCode = 1 }
}
finally {
    if ($null -ne $downloadDirectory -and (Test-Path -LiteralPath $downloadDirectory)) {
        Remove-Item -LiteralPath $downloadDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}
exit $exitCode
