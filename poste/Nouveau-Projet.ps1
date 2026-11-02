<#
    Nouveau-Projet.ps1 — crée un projet de code depuis le modèle Copier EdouardZemb/modele-projet,
    en une commande : rendu, git init avec hooks, dépôt GitHub, réglages de fusion, secret de CI,
    règle de protection de la branche principale, dossier .worktrees, ligne dans l'index.

    C'est Edouard qui le lance pour de vrai (création de dépôt, secret, règle : ses décisions).
    Une session ne le lance qu'avec -ABlanc : seules des lectures sont faites, chaque étape est
    décrite et sa commande affichée sans être exécutée.

    Usage :
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "Ce que fait l'outil"
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "..." -Visibilite prive
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "..." -Fusion edouard
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "..." -ABlanc

    -Fusion (session | edouard, défaut session) : qui fusionne les PR du projet ; passé au modèle
    (question Copier « fusion », présente depuis le lot 2 du modèle). -Cible reste « aucune ».

    Si Windows répond « l'exécution de scripts est désactivée sur ce système », lever le refus
    pour la seule fenêtre en cours, puis relancer :
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

    Les fonctions (Get-LigneIndex, Add-LigneIndex, Get-Etapes) se chargent par point-source ;
    le programme principal ne s'exécute pas dans ce cas.

    En cas d'échec après la création du dépôt (étape 5), le script s'arrête et dit ce qui est fait
    et ce qui reste. Il ne défait rien : supprimer un dépôt revient à Edouard.

    Fichier enregistré en UTF-8 AVEC BOM (Windows PowerShell 5.1).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({
        if ($_ -cmatch '^[a-z][a-z0-9-]*$') { $true }
        else { throw "Nom invalide « $_ » : il faut des minuscules, des chiffres et des tirets, en commençant par une lettre." }
    })]
    [string] $Nom,

    [Parameter(Mandatory)]
    [string] $Description,

    [ValidateSet('public', 'prive')]
    [string] $Visibilite = 'public',

    [ValidateSet('aucune')]
    [string] $Cible = 'aucune',

    [ValidateSet('session','edouard')]
    [string] $Fusion = 'session',

    [string] $Branche = 'main',

    [string] $Version,

    [string] $RacineCode = 'C:\src',

    [string] $Index = (Join-Path $HOME 'Documents\INDEX-PROJETS.md'),

    [string] $Motifs = (Join-Path $HOME '.config\modele-projet\motifs-interdits.txt'),

    [switch] $ABlanc
)

$ErrorActionPreference = 'Stop'

$Organisation = 'EdouardZemb'
$Modele       = 'EdouardZemb/modele-projet'
$Hooks        = @('.githooks/pre-commit', '.githooks/commit-msg', '.githooks/pre-push')

# ------------------------------------------------------------------ outils

function Resolve-Copier {
    $c = Get-Command copier -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $repli = Join-Path $HOME '.local\bin\copier.exe'
    if (Test-Path $repli) { return $repli }
    return $null
}

function Resolve-Python {
    # Ignore le faux python du Microsoft Store (WindowsApps) ; repli sur C:\Python312.
    $candidats = @()
    foreach ($c in @(Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($c.Source -and $c.Source -notmatch '\\WindowsApps\\') { $candidats += $c.Source }
    }
    $candidats += 'C:\Python312\python.exe'
    foreach ($c in $candidats) {
        if (-not (Test-Path -LiteralPath $c)) { continue }
        $r = Invoke-Natif $c @('--version')
        if ($r.Code -eq 0) { return $c }
    }
    return $null
}

function Invoke-Natif {
    # Lance un programme externe sans que PowerShell 5.1 transforme la sortie d'erreur en exception.
    param([string] $Exe, [string[]] $Arguments)
    $ea = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $sortie = & $Exe @Arguments 2>&1 | Out-String
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $ea
    }
    [pscustomobject]@{ Code = $code; Sortie = $sortie.Trim() }
}

function Assert-Natif {
    param([string] $Quoi, $Resultat)
    if ($Resultat.Code -ne 0) {
        throw "$Quoi a échoué (code $($Resultat.Code)).`n$($Resultat.Sortie)"
    }
}

function Protege-Guillemets([string] $Texte) {
    # Windows PowerShell 5.1 ne protège pas les guillemets d'un argument : on les échappe.
    return ($Texte -replace '"', '\"')
}

# ------------------------------------------------------------------ l'index

function Get-LigneIndex {
    param(
        [Parameter(Mandatory)] [string] $Nom,
        [Parameter(Mandatory)] [string] $Version,
        [Parameter(Mandatory)] [string] $Visibilite,
        [Parameter(Mandatory)] [string] $Date,
        [string] $RacineCode = 'C:\src'
    )
    $prive = if ($Visibilite -eq 'prive') { ' (privé)' } else { '' }
    # Concaténation plutôt que Join-Path : Windows PowerShell 5.1 refuse un lecteur absent.
    $chemin = "$($RacineCode.TrimEnd('\'))\github.com\EdouardZemb\$Nom"
    return ('| {0} | code | `{1}` — né de modele-projet {2} le {3} | EdouardZemb/{0}{4} | OUI | {3} |' -f $Nom, $chemin, $Version, $Date, $prive)
}

function Add-LigneIndex {
    # Insère la ligne après la dernière ligne du premier tableau dont l'en-tête commence par
    # « | Projet | Type | Chemin | ». Conserve l'encodage (UTF-8 sans BOM) et les fins de ligne (LF).
    param(
        [Parameter(Mandatory)] [string] $Index,
        [Parameter(Mandatory)] [string] $Ligne
    )
    $utf8 = [Text.UTF8Encoding]::new($false)
    $texte = [IO.File]::ReadAllText($Index, $utf8)
    $lignes = $texte -split "`n"

    $debut = -1
    for ($i = 0; $i -lt $lignes.Count; $i++) {
        if ($lignes[$i].StartsWith('| Projet | Type | Chemin |')) { $debut = $i; break }
    }
    if ($debut -lt 0) { throw "En-tête « | Projet | Type | Chemin | » introuvable dans $Index" }

    if ($Ligne -notmatch '^\| (.+?) \|') { throw "Ligne d'index mal formée : $Ligne" }
    $prefixe = "| $($Matches[1]) |"
    foreach ($l in $lignes) {
        if ($l.StartsWith($prefixe)) { throw "L'index contient déjà une ligne « $prefixe »." }
    }

    $fin = $debut
    while (($fin + 1) -lt $lignes.Count -and $lignes[$fin + 1].StartsWith('|')) { $fin++ }

    $liste = New-Object System.Collections.Generic.List[string]
    $liste.AddRange([string[]]$lignes)
    $liste.Insert($fin + 1, $Ligne)
    [IO.File]::WriteAllText($Index, ($liste -join "`n"), $utf8)
}

# ------------------------------------------------------------------ les étapes

function Import-Ctx {
    # À appeler par point-source : recopie le contexte des étapes dans la portée de l'appelant.
    foreach ($k in $script:Ctx.Keys) { Set-Variable -Name $k -Value $script:Ctx[$k] -Scope 1 }
}

function Get-Etapes {
    # Lit les paramètres et les valeurs dérivées dans la portée du script appelant.
    $depot   = "$Organisation/$Nom"
    $chemin  = $script:Chemin
    $pub     = if ($Visibilite -eq 'public') { '--public' } else { '--private' }
    $date    = $script:Date
    $message = "chore: naissance du projet depuis modele-projet $Version"
    $ruleset = Join-Path $chemin '.github\modele\ruleset-main.json'
    $worktrees = "$chemin.worktrees"
    $nomEtape = $Nom; $descr = $Description; $vis = $Visibilite; $cib = $Cible; $fus = $Fusion; $br = $Branche
    $ver = $Version; $mot = $Motifs; $idx = $Index; $hooks = $Hooks; $org = $Organisation; $mdl = $Modele

    $etapes = @()

    # 1. préalables
    $etapes += [pscustomobject]@{
        Description = 'préalables : copier 9.19 ou plus, gh connecté, python, fichier de motifs, dossier cible libre, dépôt distant absent'
        Commande    = "copier --version ; gh auth status ; python --version ; Test-Path `"$mot`" ; Test-Path `"$chemin`" (doit être faux) ; gh repo view $depot (doit échouer)"
        Action      = {
            . Import-Ctx
            $copier = Resolve-Copier
            if (-not $copier) { throw "copier introuvable (ni dans le PATH, ni dans $HOME\.local\bin). Installer : pipx install copier." }
            $r = Invoke-Natif $copier @('--version')
            Assert-Natif 'copier --version' $r
            if ($r.Sortie -notmatch '(\d+\.\d+(?:\.\d+)?)') { throw "Version de copier illisible : $($r.Sortie)" }
            if ([version]$Matches[1] -lt [version]'9.19') { throw "copier $($Matches[1]) est trop ancien : 9.19 ou plus." }

            Assert-Natif 'gh auth status' (Invoke-Natif 'gh' @('auth', 'status'))
            if (-not (Resolve-Python)) { throw 'python introuvable ou inutilisable (le faux python du Microsoft Store est ignore ; repli C:\Python312\python.exe).' }

            if (-not (Test-Path -LiteralPath $mot)) { throw "Fichier de motifs introuvable : $mot" }
            if ($mot -match '\s') { throw "Le chemin du fichier de motifs ne doit pas contenir d'espace : $mot" }
            if (-not (Test-Path -LiteralPath $idx)) { throw "Index introuvable : $idx" }
            if (Test-Path -LiteralPath $chemin) { throw "Le dossier cible existe déjà : $chemin" }

            $r = Invoke-Natif 'gh' @('repo', 'view', $depot)
            if ($r.Code -eq 0) { throw "Le dépôt $depot existe déjà sur GitHub." }
        }
    }

    # 2. copier copy
    $cmdCopier = "copier copy --defaults --vcs-ref $ver --data nom=$nomEtape --data `"description=$descr`" --data visibilite=$vis --data cible=$cib --data fusion=$fus --data branche_principale=$br gh:$mdl `"$chemin`""
    $etapes += [pscustomobject]@{
        Description = "copier copy : rendre le modèle $ver dans $chemin"
        Commande    = $cmdCopier
        Action      = {
            . Import-Ctx
            $copier = Resolve-Copier
            $a = @('copy', '--defaults', '--vcs-ref', $ver,
                   '--data', "nom=$nomEtape",
                   '--data', ('description=' + (Protege-Guillemets $descr)),
                   '--data', "visibilite=$vis",
                   '--data', "cible=$cib",
                   '--data', "fusion=$fus",
                   '--data', "branche_principale=$br",
                   "gh:$mdl", $chemin)
            Assert-Natif 'copier copy' (Invoke-Natif $copier $a)
        }
    }

    # 3. git init
    $etapes += [pscustomobject]@{
        Description = "git init : dépôt local, branche $br, hooks activés"
        Commande    = "git -C `"$chemin`" init -b $br ; git -C `"$chemin`" config core.hooksPath .githooks"
        Action      = {
            . Import-Ctx
            Assert-Natif 'git init' (Invoke-Natif 'git' @('-C', $chemin, 'init', '-b', $br))
            Assert-Natif 'git config core.hooksPath' (Invoke-Natif 'git' @('-C', $chemin, 'config', 'core.hooksPath', '.githooks'))
        }
    }

    # 4. premier commit (les hooks tournent déjà)
    $etapes += [pscustomobject]@{
        Description = 'premier commit : tout ajouter, hooks exécutables, commit (les hooks du projet tournent sur ce commit)'
        Commande    = "git add -A ; git update-index --chmod=+x $($hooks -join ' ') ; git commit -m `"$message`""
        Action      = {
            . Import-Ctx
            Assert-Natif 'git add' (Invoke-Natif 'git' @('-C', $chemin, 'add', '-A'))
            Assert-Natif 'git update-index --chmod=+x' (Invoke-Natif 'git' (@('-C', $chemin, 'update-index', '--chmod=+x') + $hooks))
            $r = Invoke-Natif 'git' @('-C', $chemin, 'commit', '-m', $message)
            if ($r.Code -ne 0) { throw "Le premier commit est refusé (un hook du projet a refusé ?). Rien n'est parti sur GitHub.`n$($r.Sortie)" }
        }
    }

    # 5. gh repo create (puis le premier envoi)
    $etapes += [pscustomobject]@{
        Description = "gh repo create $depot $pub : créer le dépôt GitHub (sans envoi)"
        Commande    = "gh repo create $depot $pub --description `"$descr`" --source `"$chemin`" --remote origin"
        Action      = {
            . Import-Ctx
            $r = Invoke-Natif 'gh' @('repo', 'create', $depot, $pub, '--description', (Protege-Guillemets $descr), '--source', $chemin, '--remote', 'origin')
            Assert-Natif 'gh repo create' $r
        }
    }

    # 6. réglages de fusion. Le commit de squash reprend le titre et le corps de la PR, que la CI
    #    examine, et non les messages des commits de la branche.
    $etapes += [pscustomobject]@{
        Description = 'réglages de fusion : squash seul (titre et corps de la PR), branche supprimée après fusion'
        Commande    = "gh repo edit $depot --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false --delete-branch-on-merge ; gh api -X PATCH repos/$depot -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY"
        Action      = {
            . Import-Ctx
            Assert-Natif 'gh repo edit' (Invoke-Natif 'gh' @('repo', 'edit', $depot, '--enable-squash-merge', '--enable-merge-commit=false', '--enable-rebase-merge=false', '--delete-branch-on-merge'))
            Assert-Natif 'gh api (réglages du squash)' (Invoke-Natif 'gh' @('api', '-X', 'PATCH', "repos/$depot", '-f', 'squash_merge_commit_title=PR_TITLE', '-f', 'squash_merge_commit_message=PR_BODY'))
        }
    }

    # 7. secret MOTIFS_INTERDITS, deux fois (Actions, Dependabot), par la redirection de cmd :
    #    elle transmet les octets tels quels, là où un tube PowerShell 5.1 abîmerait les accents.
    $cmdActions    = "gh secret set MOTIFS_INTERDITS --repo $depot < $mot"
    $cmdDependabot = "gh secret set MOTIFS_INTERDITS --repo $depot --app dependabot < $mot"
    $etapes += [pscustomobject]@{
        Description = 'secret MOTIFS_INTERDITS : posé pour Actions et pour Dependabot'
        Commande    = "cmd /c `"$cmdActions`" ; cmd /c `"$cmdDependabot`""
        Action      = {
            . Import-Ctx
            Assert-Natif 'secret MOTIFS_INTERDITS (Actions)' (Invoke-Natif 'cmd.exe' @('/c', $cmdActions))
            Assert-Natif 'secret MOTIFS_INTERDITS (Dependabot)' (Invoke-Natif 'cmd.exe' @('/c', $cmdDependabot))
        }
    }

    # 8. premier envoi. Le hook pre-push refuse tout envoi vers la branche principale : le tout
    #    premier envoi est la seule exception, d'où --no-verify. Il vient après le secret (la CI
    #    de main en a besoin) et avant la règle de protection (qui refuserait cet envoi direct).
    $etapes += [pscustomobject]@{
        Description = "premier envoi : pousser $br vers GitHub (--no-verify, seule exception au pre-push)"
        Commande    = "git -C `"$chemin`" push --no-verify -u origin $br"
        Action      = {
            . Import-Ctx
            Assert-Natif 'premier envoi' (Invoke-Natif 'git' @('-C', $chemin, 'push', '--no-verify', '-u', 'origin', $br))
        }
    }
    # 9. règle de protection (dépôt public seulement)
    if ($vis -eq 'public') {
        $etapes += [pscustomobject]@{
            Description = "règle de protection : appliquer ruleset-main.json à $br"
            Commande    = "gh api -X POST repos/$depot/rulesets --input `"$ruleset`""
            Action      = {
                . Import-Ctx
                Assert-Natif 'gh api rulesets' (Invoke-Natif 'gh' @('api', '-X', 'POST', "repos/$depot/rulesets", '--input', $ruleset))
            }
        }
    } else {
        $etapes += [pscustomobject]@{
            Description = 'règle de protection : sans objet (dépôt privé)'
            Commande    = '(aucune)'
            Action      = { }
        }
    }

    # 10. dossier .worktrees
    $etapes += [pscustomobject]@{
        Description = "dossier .worktrees : $worktrees"
        Commande    = "New-Item -ItemType Directory `"$worktrees`""
        Action      = {
            . Import-Ctx
            New-Item -ItemType Directory -Path $worktrees -Force | Out-Null
        }
    }

    # 11. ligne d'index
    $ligne = Get-LigneIndex -Nom $nomEtape -Version $ver -Visibilite $vis -Date $date -RacineCode $RacineCode
    $etapes += [pscustomobject]@{
        Description = "ligne d'index : ajoutée à $idx"
        Commande    = "Add-LigneIndex -Index `"$idx`" -Ligne `"$ligne`""
        Action      = {
            . Import-Ctx
            Add-LigneIndex -Index $idx -Ligne $ligne
        }
    }

    $script:Ctx = @{
        depot = $depot; chemin = $chemin; pub = $pub; message = $message; ruleset = $ruleset
        worktrees = $worktrees; nomEtape = $nomEtape; descr = $descr; vis = $vis; cib = $cib; fus = $fus
        br = $br; ver = $ver; mot = $mot; idx = $idx; hooks = $hooks; ligne = $ligne; mdl = $mdl
        cmdActions = $cmdActions; cmdDependabot = $cmdDependabot
    }
    return $etapes
}


# ------------------------------------------------------------------ programme principal

$script:Chemin = Join-Path $RacineCode "github.com\$Organisation\$Nom"
$script:Date   = Get-Date -Format 'yyyy-MM-dd'

if ($MyInvocation.InvocationName -ne '.') {

    if (-not $Version) {
        $r = Invoke-Natif 'gh' @('release', 'view', '--repo', $Modele, '--json', 'tagName', '-q', '.tagName')
        if ($r.Code -ne 0 -or -not $r.Sortie) {
            Write-Host "Impossible de déterminer la version du modèle (aucune publication ?). Passer -Version vX.Y.Z." -ForegroundColor Red
            exit 1
        }
        $Version = $r.Sortie
    }

    $etapes = @(Get-Etapes)
    $total  = $etapes.Count
    if ($ABlanc) { Write-Host "A BLANC : seules les lectures de l'étape 1 sont faites ; rien n'est créé." -ForegroundColor Yellow }
    Write-Host "Projet : $Nom ($Visibilite) -> $script:Chemin ; modèle $Version ; fusion $Fusion" -ForegroundColor Cyan

    $faites = @()
    for ($i = 0; $i -lt $total; $i++) {
        $e = $etapes[$i]
        Write-Host ''
        Write-Host ("[{0}/{1}] {2}" -f ($i + 1), $total, $e.Description) -ForegroundColor Cyan
        Write-Host ("        > {0}" -f $e.Commande) -ForegroundColor DarkGray
        if ($ABlanc -and $i -gt 0) { continue }   # à blanc : seul l'étape 1 (lectures) s'exécute
        try {
            & $e.Action
            $faites += $e.Description
            if ($ABlanc) { Write-Host '        préalables vérifiés' -ForegroundColor Green }
        } catch {
            Write-Host ''
            Write-Host "ECHEC à l'étape $($i + 1) : $($e.Description)" -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
            if ($i -ge 4) {   # à partir de gh repo create (étape 5)
                Write-Host ''
                Write-Host 'Fait :' -ForegroundColor Yellow
                $faites | ForEach-Object { Write-Host "  - $_" }
                Write-Host 'Reste à faire :' -ForegroundColor Yellow
                for ($j = $i; $j -lt $total; $j++) { Write-Host "  - $($etapes[$j].Description)" }
                Write-Host "Rien n'a été défait : reprendre à la main, ou supprimer le dépôt (décision d'Edouard)." -ForegroundColor Yellow
            }
            exit 1
        }
    }

    Write-Host ''
    if ($ABlanc) {
        Write-Host 'A blanc terminé : rien créé.' -ForegroundColor Green
    } else {
        Write-Host "Projet créé : $script:Chemin" -ForegroundColor Green
        Write-Host "Dépôt : https://github.com/$Organisation/$Nom"
    }
}
