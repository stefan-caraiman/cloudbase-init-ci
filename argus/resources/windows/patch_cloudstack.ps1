# Look for any tracebacks in the code

Import-Module C:\common.ps1
$programFilesDir = Get-ProgramDir

$cloudbaseinit = "$programFilesDir\Cloudbase Solutions\Cloudbase-Init"
$python_name = Get-Childitem $cloudbaseinit -Filter Python* -Name
$cloudstack = "$cloudbaseinit\$python_name\Lib\site-packages\cloudbaseinit\metadata\services\cloudstack.py"
$src = "self._router_ip = ip_address"
$dest = "self._router_ip = ip_address.split(':')[0]"

(Get-Content $cloudstack).replace($src, $dest) | Set-Content $cloudstack