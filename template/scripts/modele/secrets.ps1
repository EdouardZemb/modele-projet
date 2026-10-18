# secrets.ps1 : refait sur le poste un fichier de secrets chiffre par sops.
#
# Usage : powershell -NoProfile -File scripts/modele/secrets.ps1 refaire <fichier.env.enc>
#
# Les cles viennent du .cles voisin du fichier ; chaque valeur est saisie en masque et
# n'est jamais affichee (seule sa longueur l'est, pour qu'une valeur tronquee se voie).
# Retour : 0 reussite, 1 sops a echoue, 64 usage ou valeur refusee.
# Tourne sous Windows PowerShell 5.1 comme sous pwsh. Fichier en UTF-8 avec BOM, en LF.

Set-StrictMode -Version 2.0

$script:EXIT_ECHEC = 1
$script:EXIT_USAGE = 64
# Les caracteres refuses, en plus des blancs et des caracteres de controle (valeur_sure d'ancrage).
$script:INTERDITS = '"' + "'" + '\$`;&|<>()~'

function Initialize-Sortie {
    # Les messages portent des accents : la console de 5.1 est en OEM par defaut.
    try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { $null = $_ }
}

function Lire-Cles([string]$Chemin) {
    $cles = New-Object System.Collections.Generic.List[string]
    $numero = 0
    foreach ($brut in [System.IO.File]::ReadAllText($Chemin, [System.Text.Encoding]::UTF8).Split("`n")) {
        $numero++
        $ligne = $brut.Trim()
        if ($ligne.Length -eq 0 -or $ligne.StartsWith('#')) { continue }
        if ($ligne -cnotmatch '^[A-Z][A-Z0-9_]*$') {
            throw "ligne ${numero} : cle invalide (attendu : MAJUSCULES, chiffres et _)"
        }
        if ($cles.Contains($ligne)) { throw "ligne ${numero} : cle en double : $ligne" }
        $cles.Add($ligne)
    }
    return , ($cles.ToArray())
}

function Test-ValeurSure([string]$Valeur) {
    if ([string]::IsNullOrEmpty($Valeur)) { return $false }
    foreach ($c in $Valeur.ToCharArray()) {
        if ([char]::IsWhiteSpace($c) -or [char]::IsControl($c) -or $script:INTERDITS.IndexOf($c) -ge 0) {
            return $false
        }
    }
    return $true
}

function ConvertTo-Dotenv($Valeurs) {
    $texte = New-Object System.Text.StringBuilder
    foreach ($entree in $Valeurs.GetEnumerator()) {
        [void]$texte.Append($entree.Key).Append('=').Append([string]$entree.Value).Append("`n")
    }
    # UTF-8 sans BOM : sops lit ces octets tels quels (le pipeline de 5.1 les passerait en ASCII).
    return , ((New-Object System.Text.UTF8Encoding($false)).GetBytes($texte.ToString()))
}

function Invoke-Processus([string]$Exe, [string]$Arguments, [string]$Dossier, [byte[]]$Entree) {
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Exe
    $info.Arguments = $Arguments
    $info.WorkingDirectory = $Dossier
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $info.StandardErrorEncoding = New-Object System.Text.UTF8Encoding($false)
    $processus = [System.Diagnostics.Process]::Start($info)
    try {
        $sortie = $processus.StandardOutput.ReadToEndAsync()
        $erreur = $processus.StandardError.ReadToEndAsync()
        if ($null -ne $Entree) { $processus.StandardInput.BaseStream.Write($Entree, 0, $Entree.Length) }
        $processus.StandardInput.Close()
        $processus.WaitForExit()
        return [pscustomobject]@{
            Code    = $processus.ExitCode
            Sortie  = $sortie.Result
            Erreur  = $erreur.Result
        }
    }
    finally {
        $processus.Dispose()
    }
}

function Read-ValeurMasquee([string]$Cle) {
    $secure = Read-Host -AsSecureString "Valeur de $Cle (saisie masquée)"
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

function Masquer([string]$Texte, [string[]]$Valeurs) {
    foreach ($v in $Valeurs) {
        if ($v.Length -gt 0) { $Texte = $Texte.Replace($v, '***') }
    }
    return $Texte
}

function Invoke-Refaire([string]$Fichier, [scriptblock]$LireValeur) {
    Initialize-Sortie
    if (-not $LireValeur) { $LireValeur = { param($cle) Read-ValeurMasquee $cle } }

    if (-not $Fichier -or -not $Fichier.EndsWith('.env.enc')) {
        Write-Host 'usage : secrets.ps1 refaire <fichier.env.enc>'
        return $script:EXIT_USAGE
    }
    $complet = [System.IO.Path]::GetFullPath($Fichier)
    $dossier = [System.IO.Path]::GetDirectoryName($complet)
    if (-not (Test-Path -LiteralPath $dossier -PathType Container)) {
        Write-Host "dossier introuvable : $dossier"
        return $script:EXIT_USAGE
    }
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) {
        Write-Host 'git est introuvable.'
        return $script:EXIT_USAGE
    }
    $racine = Invoke-Processus $git.Source 'rev-parse --show-toplevel' $dossier $null
    if ($racine.Code -ne 0) {
        Write-Host "$dossier n'est pas dans un dépôt git."
        return $script:EXIT_USAGE
    }
    $prefixe = Invoke-Processus $git.Source 'rev-parse --show-prefix' $dossier $null
    $racineDepot = $racine.Sortie.Trim()
    $relatif = $prefixe.Sortie.Trim() + [System.IO.Path]::GetFileName($complet)

    if (-not (Test-Path -LiteralPath (Join-Path $racineDepot '.sops.yaml') -PathType Leaf)) {
        Write-Host ".sops.yaml est absent à la racine du dépôt ($racineDepot)."
        return $script:EXIT_USAGE
    }
    $fichierCles = Join-Path $dossier ([System.IO.Path]::GetFileName($complet).Replace('.env.enc', '') + '.cles')
    if (-not (Test-Path -LiteralPath $fichierCles -PathType Leaf)) {
        Write-Host "le fichier des clés est absent : $fichierCles"
        return $script:EXIT_USAGE
    }
    try { $cles = Lire-Cles $fichierCles }
    catch {
        Write-Host "$fichierCles : $($_.Exception.Message)"
        return $script:EXIT_USAGE
    }
    if ($cles.Count -eq 0) {
        Write-Host "$fichierCles ne nomme aucune clé."
        return $script:EXIT_USAGE
    }
    $sops = Get-Command sops -ErrorAction SilentlyContinue
    if (-not $sops) {
        Write-Host "sops est introuvable. Installe-le avec installer-outils.ps1 du dépôt serveur."
        return $script:EXIT_ECHEC
    }

    $valeurs = [ordered]@{}
    foreach ($cle in $cles) {
        $valeur = [string](& $LireValeur $cle)
        if (-not (Test-ValeurSure $valeur)) {
            Write-Host "${cle} : valeur refusée (vide, blanc, caractère de contrôle ou l'un de  `" ' \ `$ `` ; & | < > ( ) ~). Rien n'est écrit."
            return $script:EXIT_USAGE
        }
        $valeurs[$cle] = $valeur
        Write-Host "${cle} : $($valeur.Length) caractères"
    }

    $octets = ConvertTo-Dotenv $valeurs
    $temporaire = "$complet.tmp-" + [System.Guid]::NewGuid().ToString('N').Substring(0, 8)
    try {
        $arguments = 'encrypt --filename-override "' + $relatif + '" --input-type dotenv --output-type dotenv --output "' + $temporaire + '"'
        $resultat = Invoke-Processus $sops.Source $arguments $racineDepot $octets
        if ($resultat.Code -ne 0) {
            Write-Host "sops a échoué (code $($resultat.Code)). Le fichier n'est pas modifié."
            $message = Masquer ($resultat.Erreur + $resultat.Sortie) ([string[]]@($valeurs.Values))
            if ($message.Trim().Length -gt 0) { Write-Host $message.Trim() }
            return $script:EXIT_ECHEC
        }
        Move-Item -LiteralPath $temporaire -Destination $complet -Force
    }
    finally {
        [System.Array]::Clear($octets, 0, $octets.Length)
        if (Test-Path -LiteralPath $temporaire) { Remove-Item -LiteralPath $temporaire -Force }
    }
    Write-Host "réécrit : $Fichier ($($cles.Count) clés). À commiter dans une PR."
    return 0
}

function Invoke-Main([string[]]$Arguments) {
    if ($Arguments.Count -ge 1 -and $Arguments[0] -eq 'refaire' -and $Arguments.Count -eq 2) {
        return (Invoke-Refaire $Arguments[1] $null)
    }
    Initialize-Sortie
    Write-Host 'usage : secrets.ps1 refaire <fichier.env.enc>'
    return $script:EXIT_USAGE
}

if ($MyInvocation.InvocationName -ne '.') {
    exit (Invoke-Main $args)
}
