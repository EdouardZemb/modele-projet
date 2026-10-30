# secrets.ps1 : refait sur le poste un fichier de secrets chiffre par sops.
#
# Usage : powershell -NoProfile -File scripts/modele/secrets.ps1 refaire <fichier.env.enc>
#
# Les cles viennent du .cles voisin du fichier. Dans un depot de donnees (DEPOT_CODE dans
# scripts/modele/reglages.py), elles viennent du .cles du depot de code, dans son clone voisin :
# ..\<DEPOT_CODE>\deploiement\secrets\<env>.cles (M-0006, § 8), et le .enc s'ecrit dans secrets/.
# Chaque valeur est saisie en masque et n'est jamais affichee (seule sa longueur l'est, pour
# qu'une valeur tronquee se voie).
# Retour : 0 reussite, 1 sops a echoue, 64 usage ou valeur refusee.
# Tourne sous Windows PowerShell 5.1 comme sous pwsh. Fichier en UTF-8 avec BOM, en LF.

Set-StrictMode -Version 2.0

$script:EXIT_ECHEC = 1
$script:EXIT_USAGE = 64
# Les caracteres refuses, en plus des blancs et des caracteres de controle (valeur_sure d'ancrage).
$script:INTERDITS = '"' + "'" + '\$`;&|<>()~'

function Set-SortieUtf8 {
    # Les messages portent des accents : la console de 5.1 est en OEM par defaut.
    # Rend la page de sortie d'origine, a retablir par Restore-Sortie ($null sans console).
    $avant = $null
    try {
        $avant = [Console]::OutputEncoding
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    }
    catch { $null = $_ }
    return $avant
}

function Restore-Sortie($Avant) {
    if ($null -eq $Avant) { return }
    try { [Console]::OutputEncoding = $Avant } catch { $null = $_ }
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

function Get-DepotCode([string]$Racine) {
    # Le depot de code d'un depot de donnees : DEPOT_CODE de scripts/modele/reglages.py, lu sans
    # l'executer ; $null hors d'un depot de donnees (pas de fichier, pas de ligne lisible).
    $chemin = Join-Path $Racine 'scripts/modele/reglages.py'
    if (-not (Test-Path -LiteralPath $chemin -PathType Leaf)) { return $null }
    $texte = [System.IO.File]::ReadAllText($chemin, [System.Text.Encoding]::UTF8)
    $trouve = [regex]::Match($texte, '(?m)^DEPOT_CODE = "([a-z][a-z0-9-]*)"\r?$')
    if ($trouve.Success) { return $trouve.Groups[1].Value }
    return $null
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
    # Process.Start ecrit sur stdin avec Console.InputEncoding, preambule compris : sous la page
    # 65001 un BOM partirait vers sops. Le temps du Start, on la met a UTF-8 sans BOM.
    $entreeAvant = $null
    try {
        $entreeAvant = [Console]::InputEncoding
        [Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
    }
    catch { $null = $_ }
    try { $processus = [System.Diagnostics.Process]::Start($info) }
    finally {
        if ($null -ne $entreeAvant) {
            try { [Console]::InputEncoding = $entreeAvant } catch { $null = $_ }
        }
    }
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

function Filtrer-Message([string]$Texte, [string[]]$Valeurs) {
    # Un message qui contient une valeur saisie n'est pas montre : masquer laisserait voir
    # la fin d'une valeur contenant une autre, et une valeur courte servirait d'oracle.
    foreach ($v in $Valeurs) {
        if ($v.Length -gt 0 -and $Texte.Contains($v)) {
            return 'message de sops retenu : il contient une valeur saisie'
        }
    }
    return $Texte
}

function Invoke-Refaire([string]$Fichier, [scriptblock]$LireValeur) {
    $sortieAvant = Set-SortieUtf8
    try { return (Invoke-RefaireInterne $Fichier $LireValeur) }
    finally { Restore-Sortie $sortieAvant }
}

function Invoke-RefaireInterne([string]$Fichier, [scriptblock]$LireValeur) {
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
    $nomCles = [System.IO.Path]::GetFileName($complet).Replace('.env.enc', '') + '.cles'
    $depotCode = Get-DepotCode $racineDepot
    if ($null -ne $depotCode) {
        # Un depot de donnees : la liste des cles est celle du depot de code, dans son clone voisin.
        $voisins = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($racineDepot))
        $fichierCles = [System.IO.Path]::Combine([string[]]@($voisins, $depotCode, 'deploiement', 'secrets', $nomCles))
    }
    else {
        $fichierCles = Join-Path $dossier $nomCles
    }
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
            $message = Filtrer-Message ($resultat.Erreur + $resultat.Sortie) ([string[]]@($valeurs.Values))
            if ($message.Trim().Length -gt 0) { Write-Host $message.Trim() }
            return $script:EXIT_ECHEC
        }
        try {
            # Remplacement atomique quand le .enc existe ; une erreur rend 1.
            if (Test-Path -LiteralPath $complet) {
                [System.IO.File]::Replace($temporaire, $complet, [NullString]::Value)
            }
            else {
                [System.IO.File]::Move($temporaire, $complet)
            }
        }
        catch {
            Write-Host "le remplacement de $Fichier a échoué : $($_.Exception.Message) Le fichier n'est pas modifié."
            return $script:EXIT_ECHEC
        }
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
    $sortieAvant = Set-SortieUtf8
    Write-Host 'usage : secrets.ps1 refaire <fichier.env.enc>'
    Restore-Sortie $sortieAvant
    return $script:EXIT_USAGE
}

if ($MyInvocation.InvocationName -ne '.') {
    exit (Invoke-Main $args)
}
