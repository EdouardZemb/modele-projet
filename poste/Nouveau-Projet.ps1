<#
    Nouveau-Projet.ps1 — crée un projet depuis le modèle Copier EdouardZemb/modele-projet, en une
    commande : rendu, git init avec hooks, premier commit, dépôt GitHub, réglages de fusion, secret
    de CI, premier envoi, règle de protection de la branche principale, dossier .worktrees, ligne
    dans l'index.

    -Cible aucune (défaut) : le dépôt de code seul ; avec -Donnees, aussi le dépôt de données
    <nom>-donnees (cible donnees, cible_code aucune). -Cible serveur : toujours les deux (M-0006) ;
    le dépôt de données porte l'instance (domaine, bloc de ports, clés du parc). Le dépôt de données
    est toujours privé et en fusion session. Tout le local des deux dépôts (rendu, git init, premier
    commit) se fait avant tout geste sur GitHub.

    C'est Edouard qui le lance pour de vrai (création de dépôt, secret, règle : ses décisions).
    Une session ne le lance qu'avec -ABlanc : seules des lectures sont faites, chaque étape est
    décrite et sa commande affichée sans être exécutée.

    Usage :
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "Ce que fait l'outil"
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "..." -Visibilite prive
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "..." -Fusion edouard
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "..." -Donnees
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "..." -Cible serveur -Domaine <domaine> -CleServeur <age1…> -CleHorsLigne <age1…>
      .\Nouveau-Projet.ps1 -Nom mon-outil -Description "..." -ABlanc

    -Visibilite (public | prive, défaut public) et -Fusion (session | edouard, défaut session)
    valent pour le dépôt de code.

    -Cible serveur : -Domaine, -CleServeur et -CleHorsLigne sont obligatoires, validés comme par
    Copier ; le script n'en porte aucune valeur. -BlocPorts vaut par défaut le premier bloc libre
    des projets\*.env du clone local de serveur (-RacineServeur), lu seulement ; un bloc pris est
    refusé. -PortApp (3000), -CheminSante (/api/sante) et -SansSauvegardes vont au dépôt de code.
    La mise en service (la déclaration dans serveur, les routes, les secrets) suit exploitation.md.

    Si Windows répond « l'exécution de scripts est désactivée sur ce système », lever le refus
    pour la seule fenêtre en cours, puis relancer :
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

    Les fonctions (Get-LigneIndex, Add-LigneIndex, Get-BlocLibre, Assert-Parametres, Get-Etapes,
    Invoke-Etapes…) se chargent par point-source ; le programme principal ne s'exécute pas dans ce
    cas.

    Un échec arrête tout. À partir de la première étape sur GitHub, le script dit ce qui est fait
    et affiche les commandes qui restent. Il ne défait rien : supprimer un dépôt revient à Edouard.
    Relancé, il refuse aux préalables : on finit à la main, par les commandes affichées.

    Fichier enregistré en UTF-8 AVEC BOM (Windows PowerShell 5.1).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({
        if ($_ -cnotmatch '^[a-z][a-z0-9-]*$') { throw "Nom invalide « $_ » : il faut des minuscules, des chiffres et des tirets, en commençant par une lettre." }
        if ($_ -clike '*-') { throw "Nom invalide « $_ » : il ne doit pas finir par un tiret (copier refuserait le sous-domaine des données)." }
        if ($_ -clike '*-donnees') { throw "Nom invalide « $_ » : un nom en -donnees est réservé au dépôt de données, que le script crée lui-même (-Donnees, ou -Cible serveur)." }
        $true
    })]
    [string] $Nom,

    [Parameter(Mandatory)]
    [string] $Description,

    [ValidateSet('public', 'prive')]
    [string] $Visibilite = 'public',

    # aucune : le dépôt de code seul (avec -Donnees, aussi <nom>-donnees) ; serveur : les deux.
    [ValidateSet('aucune', 'serveur')]
    [string] $Cible = 'aucune',

    [switch] $Donnees,

    [ValidateSet('session','edouard')]
    [string] $Fusion = 'session',

    [string] $Branche = 'main',

    # -Cible serveur : l'instance, que porte le dépôt de données. Aucune valeur dans le script.
    [string] $Domaine,

    [string] $CleServeur,

    [string] $CleHorsLigne,

    # Absent (ou 0) : le premier bloc libre du clone de serveur.
    [int] $BlocPorts,

    [int] $PortApp = 3000,

    [string] $CheminSante = '/api/sante',

    [switch] $SansSauvegardes,

    [string] $Version,

    # D'où copier rend le modèle : GitHub par défaut, un dossier local pour les tests.
    [string] $SourceModele = 'gh:EdouardZemb/modele-projet',

    [string] $RacineCode = 'C:\src',

    # Le clone local de serveur, lu seulement. Absent : <RacineCode>\github.com\EdouardZemb\serveur.
    [string] $RacineServeur,

    [string] $Index = (Join-Path $HOME 'Documents\INDEX-PROJETS.md'),

    [string] $Motifs = (Join-Path $HOME '.config\modele-projet\motifs-interdits.txt'),

    [switch] $ABlanc
)

$ErrorActionPreference = 'Stop'

$Organisation = 'EdouardZemb'
$Modele       = 'EdouardZemb/modele-projet'
$Hooks        = @('.githooks/pre-commit', '.githooks/commit-msg', '.githooks/pre-push')
# Les paramètres de la seule cible serveur que l'appel a passés : refusés dans une autre cible, où
# ils seraient ignorés (un -Cible serveur oublié créerait un seul dépôt).
$ParamsServeur = @('Domaine', 'CleServeur', 'CleHorsLigne', 'BlocPorts', 'PortApp', 'CheminSante', 'SansSauvegardes' |
    Where-Object { $PSBoundParameters.ContainsKey($_) })

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

function Format-Argument([string] $Texte) {
    # Un argument d'une commande affichée, qui se colle tel quel dans PowerShell : entre apostrophes,
    # doublées, dès qu'il contient autre chose que des caractères sûrs. Rien n'y est interpolé.
    if ($Texte -cmatch '^[A-Za-z0-9_./:=+-]+$') { return $Texte }
    return "'" + ($Texte -replace "'", "''") + "'"
}

# ------------------------------------------------------------------ l'index

function Get-LigneIndex {
    param(
        [Parameter(Mandatory)] [string] $Nom,
        [Parameter(Mandatory)] [string] $Version,
        [Parameter(Mandatory)] [string] $Visibilite,
        [Parameter(Mandatory)] [string] $Date,
        [string] $RacineCode = 'C:\src',
        [ValidateSet('code', 'donnees')] [string] $Type = 'code'
    )
    $prive = if ($Visibilite -eq 'prive') { ' (privé)' } else { '' }
    $colonne = if ($Type -eq 'donnees') { 'données' } else { 'code' }
    # Concaténation plutôt que Join-Path : Windows PowerShell 5.1 refuse un lecteur absent.
    $chemin = "$($RacineCode.TrimEnd('\'))\github.com\EdouardZemb\$Nom"
    return ('| {0} | {5} | `{1}` — né de modele-projet {2} le {3} | EdouardZemb/{0}{4} | OUI | {3} |' -f $Nom, $chemin, $Version, $Date, $prive, $colonne)
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

function Assert-Index {
    # En lecture seule, dès les préalables : l'index a l'en-tête « | Projet | Type | Chemin | » et
    # aucune des lignes à ajouter. Sinon Add-LigneIndex échouerait entre deux gestes sur GitHub.
    param(
        [Parameter(Mandatory)] [string] $Index,
        [Parameter(Mandatory)] [string[]] $Lignes
    )
    $existantes = [IO.File]::ReadAllText($Index, [Text.UTF8Encoding]::new($false)) -split "`n"
    if (-not @($existantes | Where-Object { $_.StartsWith('| Projet | Type | Chemin |') }).Count) {
        throw "En-tête « | Projet | Type | Chemin | » introuvable dans $Index : la ligne d'index ne pourrait pas s'y ajouter."
    }
    foreach ($l in $Lignes) {
        if ($l -notmatch '^\| (.+?) \|') { throw "Ligne d'index mal formée : $l" }
        $prefixe = "| $($Matches[1]) |"
        if (@($existantes | Where-Object { $_.StartsWith($prefixe) }).Count) { throw "L'index contient déjà une ligne « $prefixe »." }
    }
}

# ------------------------------------------------------------------ l'instance (cible serveur)

function Get-BlocsPris {
    # Les BLOC_PORTS des projets déclarés dans le clone local de serveur, lus seulement.
    param([Parameter(Mandatory)] [string] $RacineServeur)
    $dossier = Join-Path $RacineServeur 'projets'
    if (-not (Test-Path -LiteralPath $dossier -PathType Container)) {
        throw "Clone de serveur illisible : $dossier est introuvable (voir -RacineServeur)."
    }
    $pris = @()
    foreach ($f in @(Get-ChildItem -LiteralPath $dossier -Filter '*.env' -File)) {
        foreach ($l in [IO.File]::ReadAllLines($f.FullName)) {
            if ($l -match '^BLOC_PORTS=([0-9]+)\s*$') { $pris += [int] $Matches[1] }
        }
    }
    return $pris
}

function Get-BlocLibre {
    # Le plus petit bloc de dix ports, multiple de 10 de 4310 à 4990, qu'aucun projet de serveur ne
    # prend. Une erreur si tout est pris, ou si le clone est illisible.
    param([Parameter(Mandatory)] [string] $RacineServeur)
    $pris = @(Get-BlocsPris $RacineServeur)
    for ($b = 4310; $b -le 4990; $b += 10) {
        if ($pris -notcontains $b) { return $b }
    }
    throw "Aucun bloc de ports libre de 4310 à 4990 dans $RacineServeur\projets."
}

function Assert-BlocLibre {
    param(
        [Parameter(Mandatory)] [string] $RacineServeur,
        [Parameter(Mandatory)] [int] $Bloc
    )
    if ($Bloc % 10 -ne 0 -or $Bloc -lt 4310 -or $Bloc -gt 4990) {
        throw "-BlocPorts $Bloc refusé : un multiple de 10, de 4310 à 4990."
    }
    if (@(Get-BlocsPris $RacineServeur) -contains $Bloc) {
        throw "Le bloc de ports $Bloc est déjà pris dans $RacineServeur\projets."
    }
}

function Assert-Instance {
    # Le domaine et les deux clés du parc, validés comme par Copier (copier.yml).
    param([string] $Domaine, [string] $CleServeur, [string] $CleHorsLigne)
    if (-not $Domaine) { throw '-Cible serveur : -Domaine est obligatoire.' }
    if ($Domaine -cnotmatch '^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$') {
        throw "-Domaine « $Domaine » refusé : un nom de domaine en minuscules."
    }
    $cles = [ordered]@{ '-CleServeur' = $CleServeur; '-CleHorsLigne' = $CleHorsLigne }
    foreach ($k in $cles.Keys) {
        if (-not $cles[$k]) { throw "-Cible serveur : $k est obligatoire (une clé publique age, age1…)." }
        if ($cles[$k] -cnotmatch '^age1[0-9a-z]{58}$') { throw "$k mal formée : une clé publique age (age1 et 58 caractères)." }
    }
}

function Assert-Parametres {
    # Avant toute étape : ce que Copier refuserait, et en cible serveur le bloc de ports, le premier
    # libre si -BlocPorts manque. Dans une autre cible, les paramètres de serveur sont refusés. Lit
    # les paramètres dans la portée du script appelant.
    if ($Cible -ne 'serveur') {
        if (@($ParamsServeur).Count) {
            throw "-$(@($ParamsServeur) -join ', -') : pour la cible serveur seulement. Ajouter -Cible serveur, ou retirer ces paramètres."
        }
        return
    }
    Assert-Instance -Domaine $Domaine -CleServeur $CleServeur -CleHorsLigne $CleHorsLigne
    if ($BlocPorts) { Assert-BlocLibre -RacineServeur $RacineServeur -Bloc $BlocPorts }
    else { $script:BlocPorts = Get-BlocLibre $RacineServeur }
}

# ------------------------------------------------------------------ les étapes

function Import-Ctx {
    # À appeler par point-source, au début d'une action : recopie le contexte de l'étape en cours
    # ($script:Ctx, posé par Invoke-Etapes) dans la portée de l'action, et nulle part ailleurs.
    foreach ($k in $script:Ctx.Keys) { Set-Variable -Name $k -Value $script:Ctx[$k] -Scope 0 }
}

function New-Depot {
    # Le contexte des étapes d'un dépôt : les valeurs communes et les siennes, que ses actions lisent
    # par Import-Ctx. Lit $Organisation, $RacineCode et la date dans la portée du script appelant.
    param(
        [Parameter(Mandatory)] [hashtable] $Commun,
        [Parameter(Mandatory)] [string] $NomDepot,
        [Parameter(Mandatory)] [string] $Dossier,
        [Parameter(Mandatory)] [string] $Descr,
        [Parameter(Mandatory)] [string] $Vis,
        [Parameter(Mandatory)] [string] $Type,
        [Parameter(Mandatory)] [string[]] $Reponses,
        [string] $Etiquette = ''
    )
    $ctx = $Commun.Clone()
    $ctx.nomDepot  = $NomDepot
    $ctx.depot     = "$Organisation/$NomDepot"
    $ctx.chemin    = $Dossier
    $ctx.descr     = $Descr
    $ctx.vis       = $Vis
    $ctx.pub       = if ($Vis -eq 'public') { '--public' } else { '--private' }
    $ctx.etiq      = $Etiquette
    $ctx.ruleset   = Join-Path $Dossier '.github\modele\ruleset-main.json'
    $ctx.worktrees = "$Dossier.worktrees"
    $ctx.ligne     = Get-LigneIndex -Nom $NomDepot -Version $Commun.ver -Visibilite $Vis -Date $script:Date -RacineCode $RacineCode -Type $Type
    # Le secret, par la redirection de cmd : elle transmet les octets tels quels, là où un tube
    # PowerShell 5.1 abîmerait les accents.
    $ctx.cmdActions    = "gh secret set MOTIFS_INTERDITS --repo $($ctx.depot) < $($Commun.mot)"
    $ctx.cmdDependabot = "gh secret set MOTIFS_INTERDITS --repo $($ctx.depot) --app dependabot < $($Commun.mot)"
    # copier : l'action reçoit les réponses aux guillemets protégés ; la commande affichée, collée
    # dans PowerShell, passe les mêmes arguments.
    $a = @('copy', '--defaults', '--vcs-ref', $Commun.ver)
    foreach ($r in $Reponses) { $a += @('--data', (Protege-Guillemets $r)) }
    $ctx.argsCopier = $a + @($Commun.src, $Dossier)
    $ctx.cmdCopier  = 'copier ' + (($ctx.argsCopier | ForEach-Object { Format-Argument $_ }) -join ' ')
    return $ctx
}

function Get-Etapes {
    # Lit les paramètres et les valeurs dérivées dans la portée du script appelant. Rend les étapes
    # des deux dépôts en une seule liste : les préalables ; puis tout le local, les rendus, puis le
    # git init et le premier commit de chaque dépôt ; enfin GitHub, dépôt par dépôt. Chaque étape
    # porte le contexte que lit son action (Ctx) et dit si elle agit sur GitHub.
    $serveur = ($Cible -eq 'serveur')
    $deux    = $serveur -or [bool] $Donnees
    $commun  = @{
        br = $Branche; ver = $Version; src = $SourceModele; mot = $Motifs; idx = $Index; hooks = $Hooks
        message = "chore: naissance du projet depuis modele-projet $Version"
    }

    # Le dépôt de code reçoit nature=code explicitement ; plus de visibilite, sans effet depuis la v0.6.0.
    $repCode = @("nom=$Nom", "description=$Description", "cible=$Cible", 'nature=code', "fusion=$Fusion", "branche_principale=$Branche")
    if ($serveur) {
        $sauv = if ($SansSauvegardes) { 'false' } else { 'true' }
        $repCode += @("port_app=$PortApp", "chemin_sante=$CheminSante", "sauvegardes=$sauv")
    }
    $etiqCode = if ($deux) { " ($Nom)" } else { '' }
    $depots = @(New-Depot -Commun $commun -NomDepot $Nom -Dossier $script:Chemin -Descr $Description -Vis $Visibilite -Type code -Reponses $repCode -Etiquette $etiqCode)

    # Le dépôt de données : toujours privé, toujours en fusion session (M-0006, § 1).
    if ($deux) {
        $nomD  = "$Nom-donnees"
        $descD = "Données de $Nom"
        $repD  = @("nom=$nomD", "description=$descD", 'cible=donnees', "cible_code=$Cible", 'fusion=session', "branche_principale=$Branche")
        if ($serveur) {
            $repD += @("domaine=$Domaine", "sous_domaine=$Nom", "bloc_ports=$BlocPorts", "cle_serveur=$CleServeur", "cle_hors_ligne=$CleHorsLigne")
        }
        $depots += , (New-Depot -Commun $commun -NomDepot $nomD -Dossier $script:CheminDonnees -Descr $descD -Vis 'prive' -Type donnees -Reponses $repD -Etiquette " ($nomD)")
    }

    $etapes = @()

    # 1. préalables : des lectures seulement, les seules faites à blanc
    $chemins  = @($depots | ForEach-Object { $_.chemin })
    $distants = @($depots | ForEach-Object { $_.depot })
    $ctxPre = $commun.Clone()
    $ctxPre.chemins = $chemins; $ctxPre.distants = $distants; $ctxPre.serveur = $serveur
    $ctxPre.dom = $Domaine; $ctxPre.cleS = $CleServeur; $ctxPre.cleH = $CleHorsLigne
    $ctxPre.bloc = $BlocPorts; $ctxPre.racineSrv = $RacineServeur
    $ctxPre.lignes = @($depots | ForEach-Object { $_.ligne })
    if ($deux) {
        $descPre = "préalables : copier 9.19 ou plus, gh connecté, python, fichier de motifs, dossiers cibles libres, dépôts distants absents ($(($depots | ForEach-Object { $_.nomDepot }) -join ', '))"
    } else {
        $descPre = 'préalables : copier 9.19 ou plus, gh connecté, python, fichier de motifs, dossier cible libre, dépôt distant absent'
    }
    $cmdPre = "copier --version ; gh auth status ; python --version ; Test-Path $(Format-Argument $Motifs)"
    $cmdPre += " ; Select-String -LiteralPath $(Format-Argument $Index) -SimpleMatch -Pattern '| Projet | Type | Chemin |' (doit trouver l'en-tête, sans les lignes à ajouter)"
    foreach ($c in $chemins)  { $cmdPre += " ; Test-Path $(Format-Argument $c) (doit être faux)" }
    foreach ($d in $distants) { $cmdPre += " ; gh repo view $(Format-Argument $d) (doit échouer)" }
    if ($serveur) {
        $descPre += ", domaine et clés valides, clone de serveur lisible, bloc de ports $BlocPorts libre"
        $cmdPre  += " ; Get-ChildItem $(Format-Argument "$RacineServeur\projets\*.env") (BLOC_PORTS=$BlocPorts absent)"
    }
    $etapes += [pscustomobject]@{
        Description = $descPre
        Commande    = $cmdPre
        Ctx         = $ctxPre
        GitHub      = $false
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
            Assert-Index -Index $idx -Lignes $lignes
            foreach ($c in $chemins) {
                if (Test-Path -LiteralPath $c) { throw "Le dossier cible existe déjà : $c" }
            }
            foreach ($d in $distants) {
                $r = Invoke-Natif 'gh' @('repo', 'view', $d)
                if ($r.Code -eq 0) { throw "Le dépôt $d existe déjà sur GitHub." }
            }
            if ($serveur) {
                Assert-Instance -Domaine $dom -CleServeur $cleS -CleHorsLigne $cleH
                Assert-BlocLibre -RacineServeur $racineSrv -Bloc $bloc
            }
        }
    }

    # 2. copier copy, pour chaque dépôt
    foreach ($d in $depots) {
        $etapes += [pscustomobject]@{
            Description = "copier copy$($d.etiq) : rendre le modèle $Version dans $($d.chemin)"
            Commande    = $d.cmdCopier
            Ctx         = $d
            GitHub      = $false
            Action      = {
                . Import-Ctx
                $copier = Resolve-Copier
                Assert-Natif 'copier copy' (Invoke-Natif $copier $argsCopier)
            }
        }
    }

    # 3. git init et premier commit, pour chaque dépôt. Le premier commit passe le pre-commit du
    #    dépôt, donc la porte dans le régime de sa nature, avant tout geste sur GitHub.
    foreach ($d in $depots) {
        $etapes += [pscustomobject]@{
            Description = "git init$($d.etiq) : dépôt local, branche $Branche, hooks activés"
            Commande    = "git -C $(Format-Argument $d.chemin) init -b $(Format-Argument $Branche) ; git -C $(Format-Argument $d.chemin) config core.hooksPath .githooks"
            Ctx         = $d
            GitHub      = $false
            Action      = {
                . Import-Ctx
                Assert-Natif 'git init' (Invoke-Natif 'git' @('-C', $chemin, 'init', '-b', $br))
                Assert-Natif 'git config core.hooksPath' (Invoke-Natif 'git' @('-C', $chemin, 'config', 'core.hooksPath', '.githooks'))
            }
        }
        $etapes += [pscustomobject]@{
            Description = "premier commit$($d.etiq) : tout ajouter, hooks exécutables, commit (les hooks du projet tournent sur ce commit)"
            Commande    = "git -C $(Format-Argument $d.chemin) add -A ; git -C $(Format-Argument $d.chemin) update-index --chmod=+x $($Hooks -join ' ') ; git -C $(Format-Argument $d.chemin) commit -m $(Format-Argument $d.message)"
            Ctx         = $d
            GitHub      = $false
            Action      = {
                . Import-Ctx
                Assert-Natif 'git add' (Invoke-Natif 'git' @('-C', $chemin, 'add', '-A'))
                Assert-Natif 'git update-index --chmod=+x' (Invoke-Natif 'git' (@('-C', $chemin, 'update-index', '--chmod=+x') + $hooks))
                $r = Invoke-Natif 'git' @('-C', $chemin, 'commit', '-m', $message)
                if ($r.Code -ne 0) { throw "Le premier commit est refusé (un hook du projet a refusé ?). Rien n'est parti sur GitHub.`n$($r.Sortie)" }
            }
        }
    }

    # 4. GitHub, puis le dossier .worktrees et la ligne d'index, dépôt par dépôt
    foreach ($d in $depots) {
        $etapes += [pscustomobject]@{
            Description = "gh repo create $($d.depot) $($d.pub)$($d.etiq) : créer le dépôt GitHub (sans envoi)"
            Commande    = "gh repo create $($d.depot) $($d.pub) --description $(Format-Argument (Protege-Guillemets $d.descr)) --source $(Format-Argument $d.chemin) --remote origin"
            Ctx         = $d
            GitHub      = $true
            Action      = {
                . Import-Ctx
                $r = Invoke-Natif 'gh' @('repo', 'create', $depot, $pub, '--description', (Protege-Guillemets $descr), '--source', $chemin, '--remote', 'origin')
                Assert-Natif 'gh repo create' $r
            }
        }

        # Réglages de fusion. Le commit de squash reprend le titre et le corps de la PR, que la CI
        # examine, et non les messages des commits de la branche.
        $etapes += [pscustomobject]@{
            Description = "réglages de fusion$($d.etiq) : squash seul (titre et corps de la PR), branche supprimée après fusion"
            Commande    = "gh repo edit $($d.depot) --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge=false --delete-branch-on-merge ; gh api -X PATCH repos/$($d.depot) -f squash_merge_commit_title=PR_TITLE -f squash_merge_commit_message=PR_BODY"
            Ctx         = $d
            GitHub      = $true
            Action      = {
                . Import-Ctx
                Assert-Natif 'gh repo edit' (Invoke-Natif 'gh' @('repo', 'edit', $depot, '--enable-squash-merge', '--enable-merge-commit=false', '--enable-rebase-merge=false', '--delete-branch-on-merge'))
                Assert-Natif 'gh api (réglages du squash)' (Invoke-Natif 'gh' @('api', '-X', 'PATCH', "repos/$depot", '-f', 'squash_merge_commit_title=PR_TITLE', '-f', 'squash_merge_commit_message=PR_BODY'))
            }
        }

        # Secret MOTIFS_INTERDITS, deux fois (Actions, Dependabot).
        $etapes += [pscustomobject]@{
            Description = "secret MOTIFS_INTERDITS$($d.etiq) : posé pour Actions et pour Dependabot"
            Commande    = "cmd /c $(Format-Argument $d.cmdActions) ; cmd /c $(Format-Argument $d.cmdDependabot)"
            Ctx         = $d
            GitHub      = $true
            Action      = {
                . Import-Ctx
                Assert-Natif 'secret MOTIFS_INTERDITS (Actions)' (Invoke-Natif 'cmd.exe' @('/c', $cmdActions))
                Assert-Natif 'secret MOTIFS_INTERDITS (Dependabot)' (Invoke-Natif 'cmd.exe' @('/c', $cmdDependabot))
            }
        }

        # Premier envoi. Le hook pre-push refuse tout envoi vers la branche principale : le tout
        # premier envoi est la seule exception, d'où --no-verify. Il vient après le secret (la CI
        # de la branche principale en a besoin) et avant la règle de protection (qui refuserait cet
        # envoi direct).
        $etapes += [pscustomobject]@{
            Description = "premier envoi$($d.etiq) : pousser $Branche vers GitHub (--no-verify, seule exception au pre-push)"
            Commande    = "git -C $(Format-Argument $d.chemin) push --no-verify -u origin $(Format-Argument $Branche)"
            Ctx         = $d
            GitHub      = $true
            Action      = {
                . Import-Ctx
                Assert-Natif 'premier envoi' (Invoke-Natif 'git' @('-C', $chemin, 'push', '--no-verify', '-u', 'origin', $br))
            }
        }

        # Règle de protection : un dépôt public seulement ; le dépôt de données est privé.
        if ($d.vis -eq 'public') {
            $etapes += [pscustomobject]@{
                Description = "règle de protection$($d.etiq) : appliquer ruleset-main.json à $Branche"
                Commande    = "gh api -X POST repos/$($d.depot)/rulesets --input $(Format-Argument $d.ruleset)"
                Ctx         = $d
                GitHub      = $true
                Action      = {
                    . Import-Ctx
                    Assert-Natif 'gh api rulesets' (Invoke-Natif 'gh' @('api', '-X', 'POST', "repos/$depot/rulesets", '--input', $ruleset))
                }
            }
        } else {
            $etapes += [pscustomobject]@{
                Description = "règle de protection$($d.etiq) : sans objet (dépôt privé)"
                Commande    = '(aucune)'
                Ctx         = $d
                GitHub      = $true
                Action      = { }
            }
        }

        $etapes += [pscustomobject]@{
            Description = "dossier .worktrees$($d.etiq) : $($d.worktrees)"
            Commande    = "New-Item -ItemType Directory -Force -Path $(Format-Argument $d.worktrees)"
            Ctx         = $d
            GitHub      = $false
            Action      = {
                . Import-Ctx
                New-Item -ItemType Directory -Path $worktrees -Force | Out-Null
            }
        }

        $etapes += [pscustomobject]@{
            Description = "ligne d'index$($d.etiq) : ajoutée à $Index"
            # Add-LigneIndex n'existe pas dans le shell d'Edouard : la commande dit la ligne et sa place.
            Commande    = "(à la main) dans $(Format-Argument $Index), après la dernière ligne du premier tableau « | Projet | Type | Chemin | », ajouter la ligne : $($d.ligne)"
            Ctx         = $d
            GitHub      = $false
            Action      = {
                . Import-Ctx
                Add-LigneIndex -Index $idx -Ligne $ligne
            }
        }
    }

    return $etapes
}

function Invoke-Etapes {
    # Joue les étapes dans l'ordre ; à blanc, seule la première (des lectures) s'exécute. Rend 0, ou
    # 1 au premier échec, qui arrête tout. Un échec à partir de la première étape GitHub dit ce qui
    # est fait et affiche, sous chaque étape restante, sa commande : rien n'est défait.
    param([object[]] $Etapes, [switch] $ABlanc)
    $total = $Etapes.Count
    $faites = @()
    $surGitHub = $false
    for ($i = 0; $i -lt $total; $i++) {
        $e = $Etapes[$i]
        if ($e.GitHub) { $surGitHub = $true }
        Write-Host ''
        Write-Host ("[{0}/{1}] {2}" -f ($i + 1), $total, $e.Description) -ForegroundColor Cyan
        Write-Host ("        > {0}" -f $e.Commande) -ForegroundColor DarkGray
        if ($ABlanc -and $i -gt 0) { continue }   # à blanc : seule l'étape 1 (lectures) s'exécute
        try {
            $script:Ctx = $e.Ctx
            $null = & $e.Action
            $faites += $e.Description
            if ($ABlanc) { Write-Host '        préalables vérifiés' -ForegroundColor Green }
        } catch {
            Write-Host ''
            Write-Host "ECHEC à l'étape $($i + 1) : $($e.Description)" -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
            if ($surGitHub) {
                Write-Host ''
                Write-Host 'Fait :' -ForegroundColor Yellow
                $faites | ForEach-Object { Write-Host "  - $_" }
                Write-Host 'Reste à faire :' -ForegroundColor Yellow
                for ($j = $i; $j -lt $total; $j++) {
                    Write-Host "  - $($Etapes[$j].Description)"
                    Write-Host "        > $($Etapes[$j].Commande)" -ForegroundColor DarkGray
                }
                Write-Host "Rien n'a été défait : finir à la main par ces commandes, ou supprimer les dépôts créés (décision d'Edouard)." -ForegroundColor Yellow
            }
            return 1
        }
    }
    return 0
}


# ------------------------------------------------------------------ programme principal

$script:Chemin        = Join-Path $RacineCode "github.com\$Organisation\$Nom"
$script:CheminDonnees = Join-Path $RacineCode "github.com\$Organisation\$Nom-donnees"
$script:Date          = Get-Date -Format 'yyyy-MM-dd'
if (-not $RacineServeur) { $RacineServeur = Join-Path $RacineCode "github.com\$Organisation\serveur" }

if ($MyInvocation.InvocationName -ne '.') {

    # Avant toute étape : ce que Copier refuserait, et le bloc de ports.
    try { Assert-Parametres } catch {
        Write-Host "Refus : $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }

    if (-not $Version) {
        $r = Invoke-Natif 'gh' @('release', 'view', '--repo', $Modele, '--json', 'tagName', '-q', '.tagName')
        if ($r.Code -ne 0 -or -not $r.Sortie) {
            Write-Host "Impossible de déterminer la version du modèle (aucune publication ?). Passer -Version vX.Y.Z." -ForegroundColor Red
            exit 1
        }
        $Version = $r.Sortie
    }

    $deux   = ($Cible -eq 'serveur') -or [bool] $Donnees
    $etapes = @(Get-Etapes)
    if ($ABlanc) { Write-Host "A BLANC : seules les lectures de l'étape 1 sont faites ; rien n'est créé." -ForegroundColor Yellow }
    Write-Host "Projet : $Nom ($Visibilite) -> $script:Chemin ; modèle $Version ; fusion $Fusion" -ForegroundColor Cyan
    if ($deux) {
        $instance = if ($Cible -eq 'serveur') { " ; domaine $Domaine ; bloc de ports $BlocPorts" } else { '' }
        Write-Host "Données : $Nom-donnees (prive) -> $script:CheminDonnees ; cible_code $Cible ; fusion session$instance" -ForegroundColor Cyan
    }

    if ((Invoke-Etapes -Etapes $etapes -ABlanc:$ABlanc) -ne 0) { exit 1 }

    Write-Host ''
    if ($ABlanc) {
        Write-Host 'A blanc terminé : rien créé.' -ForegroundColor Green
    } else {
        Write-Host "Projet créé : $script:Chemin" -ForegroundColor Green
        Write-Host "Dépôt : https://github.com/$Organisation/$Nom"
        if ($deux) {
            Write-Host "Données : $script:CheminDonnees" -ForegroundColor Green
            Write-Host "Dépôt : https://github.com/$Organisation/$Nom-donnees"
        }
    }
}
