<#
    Tester-Nouveau-Projet.ps1 — tests de Nouveau-Projet.ps1.
    Ne crée rien de réel : l'index est une copie temporaire, -ABlanc ne fait que lire.
    Usage : powershell -NoProfile -ExecutionPolicy Bypass -File .\Tester-Nouveau-Projet.ps1

    -SansPoste : pour la CI et les machines sans le poste d'Edouard. Saute ce qui lit gh, la liste
    privée ou l'index réel (les lancements à blanc dans un enfant), prend un index factice et rend
    le modèle depuis -SourceModele (un dépôt local) à -Version (HEAD par défaut) au lieu de v0.2.0.
#>
[CmdletBinding()]
param(
    [switch] $SansPoste,
    [string] $SourceModele = 'gh:EdouardZemb/modele-projet',
    [string] $Version
)
$ErrorActionPreference = 'Stop'
$ici     = Split-Path -Parent $MyInvocation.MyCommand.Path
$script  = Join-Path $ici 'Nouveau-Projet.ps1'
$indexReel = Join-Path $HOME 'Documents\INDEX-PROJETS.md'
$echecs  = 0
# Les paramètres du test sont recopiés : le point-source du script écrase $Version et $SourceModele.
$versionTest = $Version
$sourceTest  = $SourceModele
$sansPoste   = [bool] $SansPoste
if ($SansPoste) {
    Write-Host 'Mode -SansPoste : pas de lancement à blanc, index factice' -ForegroundColor Yellow
    if (-not $versionTest) { $versionTest = 'HEAD' }
}
$reussis = 0

function Verifier([string] $Nom, [bool] $Condition, [string] $Detail = '') {
    if ($Condition) { $script:reussis++; Write-Host "  ok    $Nom" -ForegroundColor Green }
    else { $script:echecs++; Write-Host "  ECHEC $Nom  $Detail" -ForegroundColor Red }
}

function Lancer-Enfant([string[]] $Arguments) {
    # Exécute le script dans un PowerShell enfant ; rend sortie standard et d'erreur mêlées.
    $ea = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $sortie = & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script @Arguments 2>&1 | Out-String
    $ErrorActionPreference = $ea
    return $sortie
}

function Fabriquer-Cle {
    # Une clé age de test, tirée au hasard à chaque lancement : jamais une vraie, jamais écrite ici.
    $alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
    return 'age1' + (-join (1..58 | ForEach-Object { $alphabet[(Get-Random -Maximum 36)] }))
}

function Lire-HorsContexte([object[]] $Liste) {
    # Une action ne voit que le contexte de son étape, recopié par Import-Ctx : toute variable
    # qu'elle lit sans l'affecter elle-même doit y figurer (le 17/10, « mdl » manquait : copier a reçu « gh: »).
    $automatiques = @('true', 'false', 'null', 'HOME', 'Matches', '_', 'LASTEXITCODE')
    $absentes = @()
    for ($n = 0; $n -lt $Liste.Count; $n++) {
        $ast = $Liste[$n].Action.Ast
        $affectees = @($ast.FindAll({ $args[0] -is [System.Management.Automation.Language.AssignmentStatementAst] }, $true) |
            Where-Object { $_.Left -is [System.Management.Automation.Language.VariableExpressionAst] } |
            ForEach-Object { $_.Left.VariablePath.UserPath })
        $affectees += @($ast.FindAll({ $args[0] -is [System.Management.Automation.Language.ForEachStatementAst] }, $true) |
            ForEach-Object { $_.Variable.VariablePath.UserPath })
        $lues = @($ast.FindAll({ $args[0] -is [System.Management.Automation.Language.VariableExpressionAst] }, $true) |
            ForEach-Object { $_.VariablePath.UserPath } | Sort-Object -Unique)
        $ctxEtape = $Liste[$n].Ctx
        foreach ($v in $lues) {
            if ($v -notin $affectees -and $v -notin $automatiques -and -not ($ctxEtape -and $ctxEtape.ContainsKey($v))) {
                $absentes += "étape $($n + 1) : `$$v"
            }
        }
    }
    return $absentes
}

function Indice([object[]] $Liste, [string] $Motif, [switch] $Dernier) {
    # L'indice de la première (ou de la dernière) étape dont la description commence par le motif.
    $trouve = -1
    for ($n = 0; $n -lt $Liste.Count; $n++) {
        if ($Liste[$n].Description.StartsWith($Motif, [StringComparison]::Ordinal)) {
            $trouve = $n
            if (-not $Dernier) { break }
        }
    }
    return $trouve
}

# ------------------------------------------------------------ encodage du script
Write-Host 'Encodage'
$octets = if (Test-Path $script) { [IO.File]::ReadAllBytes($script) } else { @() }
Verifier 'Nouveau-Projet.ps1 commence par EF BB BF' ($octets.Length -ge 3 -and $octets[0] -eq 0xEF -and $octets[1] -eq 0xBB -and $octets[2] -eq 0xBF)

# ------------------------------------------------------------ nom invalide
Write-Host 'Nom invalide'
$sortie = Lancer-Enfant @('-Nom', 'Mauvais_Nom', '-Description', 'x', '-ABlanc')
Verifier 'le message contient « minuscules »' ($sortie -match 'minuscules') $sortie
Verifier 'aucune étape n''a commencé' ($sortie -notmatch 'préalables') $sortie
# Le nom d'un dépôt de données est celui que le script donne lui-même au second dépôt.
$sortie = Lancer-Enfant @('-Nom', 'essai-donnees', '-Description', 'x', '-Version', 'v0.1.0', '-ABlanc')
# Le message d'erreur est coupé à la largeur de la console : on compare sur des blancs réduits.
Verifier 'nom en -donnees : refus' (($sortie -replace '\s+', ' ') -match 'r.serv. au d.p.t de donn.es') $sortie
Verifier 'nom en -donnees : aucune étape n''a commencé' ($sortie -notmatch '\[1/\d+\]') $sortie

# ------------------------------------------------------------ à blanc et fusion
# Ces lancements exécutent l'étape 1 pour de vrai (gh, liste privée) : le poste seulement.
if (-not $sansPoste) {
Write-Host 'A blanc'
$cible = 'C:\src\github.com\EdouardZemb\essai-a-blanc'
$sortie = Lancer-Enfant @('-Nom', 'essai-a-blanc', '-Description', 'Essai à blanc', '-Version', 'v0.1.0', '-ABlanc')
$attendu = @('préalables', 'copier copy', 'git init', 'premier commit',
             'gh repo create EdouardZemb/essai-a-blanc --public', 'réglages de fusion',
             'secret MOTIFS_INTERDITS', 'premier envoi', 'règle de protection', 'dossier .worktrees', "ligne d'index")
$position = -1; $ordreOk = $true; $manquant = ''
foreach ($e in $attendu) {
    $p = $sortie.IndexOf($e, $position + 1, [StringComparison]::Ordinal)
    if ($p -lt 0) { $ordreOk = $false; $manquant = $e; break }
    $position = $p
}
Verifier 'les onze étapes apparaissent dans l''ordre' $ordreOk "manquante ou dans le désordre : $manquant`n$sortie"
Verifier 'le dossier cible n''existe pas après' (-not (Test-Path $cible))
Verifier 'le récapitulatif nomme la fusion (session par défaut)' ($sortie -match 'fusion session') $sortie
Verifier 'la commande copier porte --data fusion=session' ($sortie -match '--data fusion=session') $sortie

# ------------------------------------------------------------ fusion
Write-Host 'Fusion'
$sortieEdouard = Lancer-Enfant @('-Nom', 'essai-a-blanc', '-Description', 'Essai à blanc', '-Version', 'v0.1.0', '-Fusion', 'edouard', '-ABlanc')
Verifier 'à blanc -Fusion edouard : le récapitulatif nomme la fusion' ($sortieEdouard -match 'fusion edouard') $sortieEdouard
Verifier 'à blanc -Fusion edouard : la commande copier porte --data fusion=edouard' ($sortieEdouard -match '--data fusion=edouard') $sortieEdouard
$sortieAutre = Lancer-Enfant @('-Nom', 'essai-a-blanc', '-Description', 'Essai à blanc', '-Version', 'v0.1.0', '-Fusion', 'autre', '-ABlanc')
Verifier '-Fusion autre est refusé (ValidateSet)' ($sortieAutre -match 'Fusion' -and $sortieAutre -match 'session' -and $sortieAutre -match 'edouard') $sortieAutre
Verifier '-Fusion autre : aucune étape n''a commencé' ($sortieAutre -notmatch 'préalables' -and $sortieAutre -notmatch 'copier copy') $sortieAutre
}

# ------------------------------------------------------------ fonctions, par point-source
Write-Host 'Fonctions'
. $script -Nom 'essai-fonctions' -Description 'Essai' -Version 'v0.1.0'
Verifier 'Get-LigneIndex est chargée' ($null -ne (Get-Command Get-LigneIndex -ErrorAction SilentlyContinue))
Verifier 'Add-LigneIndex est chargée' ($null -ne (Get-Command Add-LigneIndex -ErrorAction SilentlyContinue))
Verifier 'Get-Etapes est chargée'     ($null -ne (Get-Command Get-Etapes -ErrorAction SilentlyContinue))
Verifier 'Get-BlocLibre est chargée'  ($null -ne (Get-Command Get-BlocLibre -ErrorAction SilentlyContinue))
Verifier 'Invoke-Etapes est chargée'  ($null -ne (Get-Command Invoke-Etapes -ErrorAction SilentlyContinue))
Verifier 'Assert-Parametres est chargée' ($null -ne (Get-Command Assert-Parametres -ErrorAction SilentlyContinue))

if ((Get-Command Get-LigneIndex -ErrorAction SilentlyContinue) -and (Get-Command Add-LigneIndex -ErrorAction SilentlyContinue)) {
    $ligne = Get-LigneIndex -Nom 'essai-fonctions' -Version 'v0.1.0' -Visibilite 'public' -Date '2026-10-16'
    Verifier 'ligne publique : gabarit' ($ligne -eq '| essai-fonctions | code | `C:\src\github.com\EdouardZemb\essai-fonctions` — né de modele-projet v0.1.0 le 2026-10-16 | EdouardZemb/essai-fonctions | OUI | 2026-10-16 |') $ligne
    $lignePrive = Get-LigneIndex -Nom 'essai-fonctions' -Version 'v0.1.0' -Visibilite 'prive' -Date '2026-10-16'
    Verifier 'ligne privée : mention (privé)' ($lignePrive -match '\(privé\)') $lignePrive
    $ligneDonnees = $null
    try { $ligneDonnees = Get-LigneIndex -Nom 'essai-fonctions-donnees' -Version 'v0.1.0' -Visibilite 'prive' -Date '2026-10-16' -Type donnees } catch { $ligneDonnees = "$_" }
    Verifier 'ligne de données : gabarit, de type données' ($ligneDonnees -eq '| essai-fonctions-donnees | données | `C:\src\github.com\EdouardZemb\essai-fonctions-donnees` — né de modele-projet v0.1.0 le 2026-10-16 | EdouardZemb/essai-fonctions-donnees (privé) | OUI | 2026-10-16 |') $ligneDonnees
    $ligneAilleurs = Get-LigneIndex -Nom 'essai-fonctions' -Version 'v0.1.0' -Visibilite 'public' -Date '2026-10-16' -RacineCode 'D:\code\'
    Verifier 'ligne : le chemin suit -RacineCode' ($ligneAilleurs.Contains('`D:\code\github.com\EdouardZemb\essai-fonctions`')) $ligneAilleurs

    # Index fixe et octets attendus, écrits à la main : l'oracle ne recopie pas l'algorithme.
    $fixe = Join-Path ([IO.Path]::GetTempPath()) ("index-fixe-{0}.md" -f [guid]::NewGuid())
    try {
        $texteFixe = "# Dépôts`n`n| Projet | Type | Chemin |`n|---|---|---|`n| a | code | ``x`` |`n| b | doc | ``y`` |`n`nUn paragraphe.`n`n| Dossier | Raison |`n|---|---|`n| z | é |`n"
        [IO.File]::WriteAllText($fixe, $texteFixe, [Text.UTF8Encoding]::new($false))
        Add-LigneIndex -Index $fixe -Ligne '| c | code | né |'
        $attenduFixe = [byte[]](
            0x23, 0x20, 0x44, 0xC3, 0xA9, 0x70, 0xC3, 0xB4, 0x74, 0x73, 0x0A,                    # « # Dépôts »
            0x0A,
            0x7C, 0x20, 0x50, 0x72, 0x6F, 0x6A, 0x65, 0x74, 0x20, 0x7C, 0x20, 0x54, 0x79, 0x70,   # « | Projet | Typ
            0x65, 0x20, 0x7C, 0x20, 0x43, 0x68, 0x65, 0x6D, 0x69, 0x6E, 0x20, 0x7C, 0x0A,         #   e | Chemin | »
            0x7C, 0x2D, 0x2D, 0x2D, 0x7C, 0x2D, 0x2D, 0x2D, 0x7C, 0x2D, 0x2D, 0x2D, 0x7C, 0x0A,   # « |---|---|---| »
            0x7C, 0x20, 0x61, 0x20, 0x7C, 0x20, 0x63, 0x6F, 0x64, 0x65, 0x20, 0x7C, 0x20, 0x60,   # « | a | code | `
            0x78, 0x60, 0x20, 0x7C, 0x0A,                                                        #   x` | »
            0x7C, 0x20, 0x62, 0x20, 0x7C, 0x20, 0x64, 0x6F, 0x63, 0x20, 0x7C, 0x20, 0x60, 0x79,   # « | b | doc | `y
            0x60, 0x20, 0x7C, 0x0A,                                                              #   ` | »
            0x7C, 0x20, 0x63, 0x20, 0x7C, 0x20, 0x63, 0x6F, 0x64, 0x65, 0x20, 0x7C, 0x20, 0x6E,   # « | c | code | n
            0xC3, 0xA9, 0x20, 0x7C, 0x0A,                                                        #   é | » : la ligne ajoutée
            0x0A,
            0x55, 0x6E, 0x20, 0x70, 0x61, 0x72, 0x61, 0x67, 0x72, 0x61, 0x70, 0x68, 0x65, 0x2E,   # « Un paragraphe. »
            0x0A,
            0x0A,
            0x7C, 0x20, 0x44, 0x6F, 0x73, 0x73, 0x69, 0x65, 0x72, 0x20, 0x7C, 0x20, 0x52, 0x61,   # « | Dossier | Ra
            0x69, 0x73, 0x6F, 0x6E, 0x20, 0x7C, 0x0A,                                            #   ison | »
            0x7C, 0x2D, 0x2D, 0x2D, 0x7C, 0x2D, 0x2D, 0x2D, 0x7C, 0x0A,                         # « |---|---| »
            0x7C, 0x20, 0x7A, 0x20, 0x7C, 0x20, 0xC3, 0xA9, 0x20, 0x7C, 0x0A                    # « | z | é | », saut final
        )
        $obtenuFixe = [IO.File]::ReadAllBytes($fixe)
        $egalFixe = ($obtenuFixe.Length -eq $attenduFixe.Length)
        if ($egalFixe) { for ($i = 0; $i -lt $obtenuFixe.Length; $i++) { if ($obtenuFixe[$i] -ne $attenduFixe[$i]) { $egalFixe = $false; break } } }
        Verifier 'index fixe : octets écrits à la main, ligne après le premier tableau, saut final gardé' $egalFixe "attendu $($attenduFixe.Length) octets, obtenu $($obtenuFixe.Length)"
    } finally {
        Remove-Item $fixe -ErrorAction SilentlyContinue
    }

    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("index-test-{0}.md" -f [guid]::NewGuid())
    try {
        if ($sansPoste) {
            # Index factice : deux tableaux, un paragraphe, pas de donnée réelle.
            $factice = "# Dépôts`n`n| Projet | Type | Chemin |`n|---|---|---|`n| a | code | ``x`` |`n`nUn paragraphe.`n`n| Dossier | Raison |`n|---|---|`n| z | é |`n"
            [IO.File]::WriteAllText($tmp, $factice, [Text.UTF8Encoding]::new($false))
        } else {
            Copy-Item $indexReel $tmp
        }
        $avant = [IO.File]::ReadAllBytes($tmp)
        $texteAvant = [IO.File]::ReadAllText($tmp, [Text.UTF8Encoding]::new($false))
        Add-LigneIndex -Index $tmp -Ligne $ligne
        $apres = [IO.File]::ReadAllBytes($tmp)

        # attendu : la ligne insérée après la dernière ligne du premier tableau
        $lignes = $texteAvant -split "`n"
        $debut = -1
        for ($i = 0; $i -lt $lignes.Count; $i++) { if ($lignes[$i].StartsWith('| Projet | Type | Chemin |')) { $debut = $i; break } }
        $fin = $debut
        while (($fin + 1) -lt $lignes.Count -and $lignes[$fin + 1].StartsWith('|')) { $fin++ }
        $liste = New-Object System.Collections.Generic.List[string]
        $liste.AddRange([string[]]$lignes)
        $liste.Insert($fin + 1, $ligne)
        $attenduOctets = [Text.UTF8Encoding]::new($false).GetBytes(($liste -join "`n"))

        $egal = ($attenduOctets.Length -eq $apres.Length)
        if ($egal) { for ($i = 0; $i -lt $apres.Length; $i++) { if ($apres[$i] -ne $attenduOctets[$i]) { $egal = $false; break } } }
        Verifier 'octets = original + la ligne après le premier tableau, rien d''autre' $egal "attendu $($attenduOctets.Length) octets, obtenu $($apres.Length)"
        Verifier 'pas de BOM' (-not ($apres.Length -ge 3 -and $apres[0] -eq 0xEF -and $apres[1] -eq 0xBB -and $apres[2] -eq 0xBF))
        Verifier 'aucun 0x0D' (($apres | Where-Object { $_ -eq 0x0D }).Count -eq 0)
        Verifier 'l''original n''avait pas de BOM ni de CR (témoin)' (-not ($avant[0] -eq 0xEF) -and (($avant | Where-Object { $_ -eq 0x0D }).Count -eq 0))

        $erreur = $null
        try { Add-LigneIndex -Index $tmp -Ligne $ligne } catch { $erreur = $_ }
        Verifier 'une seconde insertion du même nom lève une erreur' ($null -ne $erreur)
        $apres2 = [IO.File]::ReadAllBytes($tmp)
        Verifier 'et ne modifie rien' ($apres2.Length -eq $apres.Length)

        # en-tête introuvable
        $tmp2 = Join-Path ([IO.Path]::GetTempPath()) ("index-test-{0}.md" -f [guid]::NewGuid())
        [IO.File]::WriteAllText($tmp2, "# rien`n`n| A | B |`n|---|---|`n", [Text.UTF8Encoding]::new($false))
        $erreur2 = $null
        try { Add-LigneIndex -Index $tmp2 -Ligne $ligne } catch { $erreur2 = $_ }
        Verifier 'en-tête introuvable : erreur' ($null -ne $erreur2)
        Remove-Item $tmp2 -ErrorAction SilentlyContinue
    } finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
}

# ------------------------------------------------------------ les étapes, en trois formes
# Un faux clone de serveur, dans un dossier temporaire : deux projets y prennent 4310 et 4320 ; un
# second prend tous les blocs. Le vrai clone n'est jamais lu ici.
$racineFaux  = Join-Path ([IO.Path]::GetTempPath()) ("faux-serveur-{0}" -f [guid]::NewGuid())
$fauxServeur = Join-Path $racineFaux 'serveur'
$fauxPlein   = Join-Path $racineFaux 'plein'
$cleTest1 = Fabriquer-Cle
$cleTest2 = Fabriquer-Cle
try {
    New-Item -ItemType Directory -Path (Join-Path $fauxServeur 'projets') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $fauxPlein 'projets') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $fauxServeur 'projets\a.env'), "NOM=a`nBLOC_PORTS=4310`n")
    [IO.File]::WriteAllText((Join-Path $fauxServeur 'projets\b.env'), "NOM=b`nBLOC_PORTS=4320`n")
    [IO.File]::WriteAllText((Join-Path $fauxPlein 'projets\tous.env'), ((0..68 | ForEach-Object { "BLOC_PORTS=$(4310 + 10 * $_)" }) -join "`n"))
    $argsServeur = @{ Cible = 'serveur'; Domaine = 'exemple.org'; CleServeur = $cleTest1; CleHorsLigne = $cleTest2; RacineServeur = $fauxServeur }
    $etapesA = @(); $etapesB = @(); $etapesS = @()

    # -- aucune : le dépôt de code seul, les onze étapes d'aujourd'hui
    Write-Host 'Etapes : aucune'
    try { . $script -Nom 'essai-fonctions' -Description 'Essai' -Version 'v0.1.0' } catch { Write-Host "  point-source : $_" -ForegroundColor Red }
    try { $etapesA = @(Get-Etapes) } catch { Write-Host "  Get-Etapes : $_" -ForegroundColor Red }
    $ordreA = @('préalables', 'copier copy', 'git init', 'premier commit', 'gh repo create EdouardZemb/essai-fonctions --public',
                'réglages de fusion', 'secret MOTIFS_INTERDITS', 'premier envoi', 'règle de protection', 'dossier .worktrees', "ligne d'index")
    $ordreOkA = ($etapesA.Count -eq $ordreA.Count)
    if ($ordreOkA) { for ($n = 0; $n -lt $ordreA.Count; $n++) { if (-not $etapesA[$n].Description.StartsWith($ordreA[$n], [StringComparison]::Ordinal)) { $ordreOkA = $false } } }
    Verifier 'aucune : onze étapes, dans l''ordre d''aujourd''hui' $ordreOkA (($etapesA | ForEach-Object { $_.Description }) -join "`n")
    $copierA = if ($etapesA.Count -gt 1) { $etapesA[1].Commande } else { '' }
    Verifier 'la commande copier ne porte plus visibilite' ($copierA -and $copierA -notmatch 'visibilite') $copierA
    Verifier 'la commande copier porte nature=code' ($copierA -match '--data nature=code ') $copierA
    Verifier 'la commande copier part de gh:EdouardZemb/modele-projet par défaut' ($copierA -match ' gh:EdouardZemb/modele-projet ') $copierA
    $ghA = (@($etapesA | ForEach-Object { $_.GitHub -eq $true }) -join ',')
    Verifier 'aucune : les étapes GitHub sont de la 5e à la 9e' ($ghA -eq 'False,False,False,False,True,True,True,True,True,False,False') $ghA

    # -- aucune -Donnees : deux dépôts, les données en cible donnees
    Write-Host 'Etapes : aucune -Donnees'
    try { . $script -Nom 'essai' -Description 'Essai' -Version 'v0.1.0' -Donnees -Fusion edouard } catch { Write-Host "  point-source : $_" -ForegroundColor Red }
    try { $etapesB = @(Get-Etapes) } catch { Write-Host "  Get-Etapes : $_" -ForegroundColor Red }
    Verifier 'aucune -Donnees : 21 étapes' ($etapesB.Count -eq 21) "$($etapesB.Count)"
    $creationsB = @($etapesB | Where-Object { $_.Description -like 'gh repo create*' })
    Verifier 'aucune -Donnees : deux dépôts, le code public, les données privées' ($creationsB.Count -eq 2 -and $creationsB[0].Commande -match 'EdouardZemb/essai --public ' -and $creationsB[1].Commande -match 'EdouardZemb/essai-donnees --private ') (($creationsB | ForEach-Object { $_.Commande }) -join "`n")
    $copiesB = @($etapesB | Where-Object { $_.Description -like 'copier copy*' })
    $codeB    = if ($copiesB.Count -eq 2) { $copiesB[0].Commande } else { '' }
    $donneesB = if ($copiesB.Count -eq 2) { $copiesB[1].Commande } else { '' }
    Verifier 'aucune -Donnees : deux dépôts ; les données en cible donnees, cible_code aucune, fusion session' ($donneesB -match '--data nom=essai-donnees ' -and $donneesB -match '--data cible=donnees ' -and $donneesB -match '--data cible_code=aucune ' -and $donneesB -match '--data fusion=session ' -and $donneesB -match '"description=Données de essai"') $donneesB
    Verifier 'aucune -Donnees : le code garde sa fusion (edouard), cible aucune, nature code' ($codeB -match '--data fusion=edouard ' -and $codeB -match '--data cible=aucune ' -and $codeB -match '--data nature=code ') $codeB
    Verifier 'aucune -Donnees : les données sans instance (ni domaine, ni bloc, ni clé)' ($donneesB -and $donneesB -notmatch 'domaine=|bloc_ports|cle_serveur|cle_hors_ligne') $donneesB

    # -- serveur : toujours les deux dépôts ; les données portent l'instance
    Write-Host 'Etapes : serveur'
    try { . $script -Nom 'essai' -Description 'Essai' -Version 'v0.1.0' @argsServeur } catch { Write-Host "  point-source : $_" -ForegroundColor Red }
    $refusS = $null
    try { Assert-Parametres } catch { $refusS = $_.Exception.Message }
    Verifier 'serveur : les paramètres passent, le bloc est le premier libre (4330)' ($null -eq $refusS -and $BlocPorts -eq 4330) "$refusS / bloc $BlocPorts"
    try { $etapesS = @(Get-Etapes) } catch { Write-Host "  Get-Etapes : $_" -ForegroundColor Red }
    Verifier 'serveur : 21 étapes' ($etapesS.Count -eq 21) "$($etapesS.Count)"
    $premierGH = -1
    for ($n = 0; $n -lt $etapesS.Count; $n++) { if ($etapesS[$n].GitHub -eq $true) { $premierGH = $n; break } }
    $dernierCommit    = Indice $etapesS 'premier commit' -Dernier
    $premiereCreation = Indice $etapesS 'gh repo create'
    Verifier 'serveur : aucune étape GitHub avant le dernier premier commit' ($dernierCommit -ge 0 -and $premiereCreation -gt $dernierCommit -and $premierGH -eq $premiereCreation) "dernier premier commit $dernierCommit, première gh repo create $premiereCreation, première étape GitHub $premierGH"
    $copiesS = @($etapesS | Where-Object { $_.Description -like 'copier copy*' })
    $codeS    = if ($copiesS.Count -eq 2) { $copiesS[0].Commande } else { '' }
    $donneesS = if ($copiesS.Count -eq 2) { $copiesS[1].Commande } else { '' }
    Verifier 'serveur : le code porte nature=code et cible=serveur' ($codeS -match '--data nature=code ' -and $codeS -match '--data cible=serveur ' -and $codeS -match '--data port_app=3000 ' -and $codeS -match '--data chemin_sante=/api/sante ' -and $codeS -match '--data sauvegardes=true ' -and $codeS -notmatch 'domaine|bloc_ports|cle_|visibilite') $codeS
    Verifier 'serveur : les données portent cible_code=serveur, domaine, bloc_ports, les deux clés et fusion=session' ($donneesS -match '--data cible=donnees ' -and $donneesS -match '--data cible_code=serveur ' -and $donneesS -match '--data domaine=exemple\.org ' -and $donneesS -match '--data sous_domaine=essai ' -and $donneesS -match '--data bloc_ports=4330 ' -and $donneesS.Contains("--data cle_serveur=$cleTest1 ") -and $donneesS.Contains("--data cle_hors_ligne=$cleTest2 ") -and $donneesS -match '--data fusion=session ' -and $donneesS -notmatch 'port_app|chemin_sante|sauvegardes|nature') $donneesS
    $reglesS = @($etapesS | Where-Object { $_.Description -like 'règle de protection*' })
    Verifier 'serveur : la règle de protection pour le code public, sans objet pour les données' ($reglesS.Count -eq 2 -and $reglesS[0].Commande -match 'repos/EdouardZemb/essai/rulesets' -and $reglesS[1].Description -match 'sans objet') (($reglesS | ForEach-Object { "$($_.Description) > $($_.Commande)" }) -join "`n")
    $lignesS = @($etapesS | Where-Object { $_.Description -like "ligne d'index*" })
    Verifier 'serveur : deux lignes d''index, la seconde de type données' ($lignesS.Count -eq 2 -and $lignesS[0].Commande.Contains('| essai | code |') -and $lignesS[1].Commande.Contains('| essai-donnees | données |') -and $lignesS[1].Commande.Contains('EdouardZemb/essai-donnees (privé)')) (($lignesS | ForEach-Object { $_.Commande }) -join "`n")
    $ghFaux = @($etapesS | Where-Object { ($_.GitHub -eq $true) -ne [bool]($_.Description -match '^(gh repo create|réglages de fusion|secret MOTIFS_INTERDITS|premier envoi|règle de protection)') })
    Verifier 'serveur : GitHub vrai pour la création, la fusion, le secret, l''envoi et la règle, seulement' ($etapesS.Count -gt 0 -and $ghFaux.Count -eq 0) (($ghFaux | ForEach-Object { $_.Description }) -join "`n")
    $sansNom = @($etapesS | Select-Object -Skip 1 | Where-Object { $_.Description -notmatch '\((essai|essai-donnees)\) : ' })
    $deDonnees = @($etapesS | Where-Object { $_.Description -match '\(essai-donnees\) : ' })
    Verifier 'serveur : chaque description nomme son dépôt (dix pour les données)' ($etapesS.Count -gt 0 -and $sansNom.Count -eq 0 -and $deDonnees.Count -eq 10) (($sansNom | ForEach-Object { $_.Description }) -join "`n")
    $sansSauv = ''
    try {
        . $script -Nom 'essai' -Description 'Essai' -Version 'v0.1.0' -SansSauvegardes -BlocPorts 4330 @argsServeur
        $sansSauv = @(Get-Etapes | Where-Object { $_.Description -like 'copier copy*' })[0].Commande
    } catch { $sansSauv = "$_" }
    Verifier 'serveur -SansSauvegardes : sauvegardes=false' ($sansSauv -match '--data sauvegardes=false ') $sansSauv

    # -- les trois formes
    foreach ($forme in @(@{ Nom = 'aucune'; Etapes = $etapesA }, @{ Nom = 'aucune -Donnees'; Etapes = $etapesB }, @{ Nom = 'serveur'; Etapes = $etapesS })) {
        $liste = @($forme.Etapes)
        Verifier "$($forme.Nom) : chaque étape a Description, Commande, Action, Ctx et GitHub" ($liste.Count -gt 0 -and @($liste | Where-Object { $_.Description -and $_.Commande -and $_.Action -and ($_.Ctx -is [hashtable]) -and ($_.GitHub -is [bool]) }).Count -eq $liste.Count)
        $hors = @(Lire-HorsContexte $liste)
        Verifier "chaque variable lue par une action est dans le contexte ($($forme.Nom))" ($liste.Count -gt 0 -and $hors.Count -eq 0) ($hors -join ', ')
    }

    # -- les refus, avant toute étape : dans un enfant, à blanc, sur le faux clone
    Write-Host 'Refus avant toute étape'
    $baseEnfant = @('-Nom', 'essai', '-Description', 'Essai', '-Version', 'v0.1.0', '-Cible', 'serveur',
                    '-RacineCode', (Join-Path $racineFaux 'code'), '-RacineServeur', $fauxServeur, '-ABlanc')
    foreach ($cas in @(
            @{ Nom = 'serveur sans -Domaine';      Args = @('-CleServeur', $cleTest1, '-CleHorsLigne', $cleTest2);                          Attendu = '-Domaine est obligatoire' },
            @{ Nom = 'serveur sans -CleServeur';   Args = @('-Domaine', 'exemple.org', '-CleHorsLigne', $cleTest2);                         Attendu = '-CleServeur est obligatoire' },
            @{ Nom = 'serveur sans -CleHorsLigne'; Args = @('-Domaine', 'exemple.org', '-CleServeur', $cleTest1);                           Attendu = '-CleHorsLigne est obligatoire' },
            @{ Nom = 'une clé mal formée';         Args = @('-Domaine', 'exemple.org', '-CleServeur', 'age1-pas-une-cle', '-CleHorsLigne', $cleTest2); Attendu = '-CleServeur mal form' },
            @{ Nom = 'un domaine mal formé';       Args = @('-Domaine', 'Exemple.ORG', '-CleServeur', $cleTest1, '-CleHorsLigne', $cleTest2); Attendu = 'un nom de domaine en minuscules' },
            @{ Nom = 'un -BlocPorts déjà pris';    Args = @('-Domaine', 'exemple.org', '-CleServeur', $cleTest1, '-CleHorsLigne', $cleTest2, '-BlocPorts', '4320'); Attendu = 'bloc de ports 4320' })) {
        $sortie = Lancer-Enfant ($baseEnfant + $cas.Args)
        Verifier "$($cas.Nom) : refus avant toute étape" (($sortie -replace '\s+', ' ') -match [regex]::Escape($cas.Attendu) -and $sortie -notmatch '\[1/\d+\]') $sortie
    }

    # -- Get-BlocLibre, sur le faux clone
    Write-Host 'Get-BlocLibre'
    $blocLibre = $null
    try { $blocLibre = Get-BlocLibre $fauxServeur } catch { $blocLibre = "$_" }
    Verifier 'Get-BlocLibre : 4310 et 4320 pris donnent 4330' ($blocLibre -is [int] -and $blocLibre -eq 4330) "$blocLibre"
    $erreurPlein = $null
    try { $null = Get-BlocLibre $fauxPlein } catch { $erreurPlein = $_ }
    Verifier 'Get-BlocLibre : tout pris, une erreur' ($null -ne $erreurPlein -and "$erreurPlein" -match '4990') "$erreurPlein"
    $erreurAbsent = $null
    try { $null = Get-BlocLibre (Join-Path $racineFaux 'absent') } catch { $erreurAbsent = $_ }
    Verifier 'Get-BlocLibre : un clone illisible, une erreur' ($null -ne $erreurAbsent -and "$erreurAbsent" -match 'serveur') "$erreurAbsent"

    # -- Invoke-Etapes, sur de fausses étapes
    Write-Host 'Invoke-Etapes'
    $script:troisJouee = $false
    $fausses = @(
        [pscustomobject]@{ Description = 'fausse un';    Commande = 'commande-un';    Action = { };                             Ctx = @{}; GitHub = $true },
        [pscustomobject]@{ Description = 'fausse deux';  Commande = 'commande-deux';  Action = { throw 'boum' };                Ctx = @{}; GitHub = $true },
        [pscustomobject]@{ Description = 'fausse trois'; Commande = 'commande-trois'; Action = { $script:troisJouee = $true }; Ctx = @{}; GitHub = $false })
    $flux = @()
    try { $flux = @(Invoke-Etapes -Etapes $fausses 6>&1) } catch { $flux = @("$_") }
    $codeInv  = @($flux | Where-Object { $_ -is [int] })
    $texteInv = (@($flux | Where-Object { $_ -isnot [int] } | ForEach-Object { "$_" }) -join "`n")
    Verifier 'Invoke-Etapes : un échec affiche les commandes restantes' ($texteInv.Contains('Reste à faire') -and $texteInv.Contains('commande-trois') -and $texteInv.Contains('Fait :') -and $texteInv.Contains('fausse un')) $texteInv
    Verifier 'Invoke-Etapes : l''échec rend 1 et arrête tout' ($codeInv.Count -eq 1 -and $codeInv[0] -eq 1 -and -not $script:troisJouee) "code $($codeInv -join ',') ; trois jouée : $script:troisJouee"
    $locales = @(
        [pscustomobject]@{ Description = 'locale'; Commande = 'commande-locale'; Action = { throw 'boum' }; Ctx = @{}; GitHub = $false },
        [pscustomobject]@{ Description = 'distante'; Commande = 'commande-distante'; Action = { }; Ctx = @{}; GitHub = $true })
    $flux = @()
    try { $flux = @(Invoke-Etapes -Etapes $locales 6>&1) } catch { $flux = @("$_") }
    $texteInv = (@($flux | Where-Object { $_ -isnot [int] } | ForEach-Object { "$_" }) -join "`n")
    Verifier 'Invoke-Etapes : un échec avant toute étape GitHub n''affiche pas de reste' ($texteInv.Contains('ECHEC') -and -not $texteInv.Contains('Reste à faire')) $texteInv

    # -- rendu réel, cible serveur : copier seul, les deux dépôts, dans un dossier temporaire
    # Le script passe nature (v0.6.0) et les réponses du dépôt de données d'un projet serveur
    # (v0.7.0) : sans -SansPoste, on rend v0.7.0, la première version qui les a.
    Write-Host 'Rendu serveur (copier copy seul, dossier temporaire)'
    $versionRenduServeur = if ($versionTest) { $versionTest } else { 'v0.7.0' }
    $racineRenduServeur = Join-Path $racineFaux 'rendu'
    $erreurRendu = $null
    try {
        . $script -Nom 'essai' -Description 'Essai' -Version $versionRenduServeur -SourceModele $sourceTest -RacineCode $racineRenduServeur @argsServeur
        Assert-Parametres
        foreach ($e in @(Get-Etapes | Where-Object { $_.Description -like 'copier copy*' })) {
            $script:Ctx = $e.Ctx
            $null = & $e.Action
        }
    } catch { $erreurRendu = $_.Exception.Message }
    $dossierCode    = "$script:Chemin"
    $dossierDonnees = "$script:CheminDonnees"
    $reponsesCode    = if ($dossierCode)    { Join-Path $dossierCode '.copier-answers.yml' } else { '' }
    $reponsesDonnees = if ($dossierDonnees) { Join-Path $dossierDonnees '.copier-answers.yml' } else { '' }
    $texteCode    = if ($reponsesCode -and (Test-Path -LiteralPath $reponsesCode)) { [IO.File]::ReadAllText($reponsesCode) } else { '' }
    $texteDonnees = if ($reponsesDonnees -and (Test-Path -LiteralPath $reponsesDonnees)) { [IO.File]::ReadAllText($reponsesDonnees) } else { '' }
    Verifier 'rendu serveur : le code dit nature: code, cible: serveur, et n''a pas domaine' ($texteCode -match '(?m)^nature: code\s*$' -and $texteCode -match '(?m)^cible: serveur\s*$' -and $texteCode -notmatch '(?m)^domaine:') "$erreurRendu`n$texteCode"
    Verifier 'rendu serveur : les données disent cible: donnees, cible_code: serveur, bloc_ports: 4330, domaine: exemple.org' ($texteDonnees -match '(?m)^cible: donnees\s*$' -and $texteDonnees -match '(?m)^cible_code: serveur\s*$' -and $texteDonnees -match '(?m)^bloc_ports: 4330\s*$' -and $texteDonnees -match '(?m)^domaine: exemple\.org\s*$') "$erreurRendu`n$texteDonnees"
    Verifier 'rendu serveur : les données ont env/prod.env' ($dossierDonnees -and (Test-Path -LiteralPath (Join-Path $dossierDonnees 'env\prod.env'))) "$erreurRendu"
} finally {
    if (Test-Path -LiteralPath $racineFaux) { Remove-Item -LiteralPath $racineFaux -Recurse -Force -ErrorAction SilentlyContinue }
}

# ------------------------------------------------------------ rendu réel de la fusion
# Seule l'étape « copier copy » est exécutée, dans un dossier temporaire ; rien ne part sur GitHub.
# v0.1.0 n'a pas la question « fusion » : on rend v0.2.0, la première version qui l'a.
Write-Host 'Rendu de la fusion (copier copy seul, dossier temporaire)'
$versionRendu = if ($versionTest) { $versionTest } else { 'v0.2.0' }
$racineRendu = Join-Path ([IO.Path]::GetTempPath()) ("rendu-fusion-{0}" -f [guid]::NewGuid())
try {
    foreach ($cas in @(@{ Nom = 'essai-fusion-edouard'; Args = @{ Fusion = 'edouard' }; Attendu = 'edouard' },
                       @{ Nom = 'essai-fusion-defaut';  Args = @{};                    Attendu = 'session' })) {
        $argsCas = $cas.Args
        . $script -Nom $cas.Nom -Description 'Essai' -Version $versionRendu -SourceModele $sourceTest -RacineCode $racineRendu @argsCas
        $etapesRendu = @(Get-Etapes)
        $erreurRendu = $null
        try { $script:Ctx = $etapesRendu[1].Ctx; $null = & $etapesRendu[1].Action } catch { $erreurRendu = $_.Exception.Message }
        $reponses = Join-Path $script:Chemin '.copier-answers.yml'
        $texteRendu = if (Test-Path -LiteralPath $reponses) { [IO.File]::ReadAllText($reponses) } else { '' }
        Verifier "rendu $($cas.Nom) : .copier-answers.yml porte fusion: $($cas.Attendu)" ($texteRendu -match "(?m)^fusion: $($cas.Attendu)\s*$") "$erreurRendu`n$texteRendu"
    }
} finally {
    if (Test-Path -LiteralPath $racineRendu) { Remove-Item -LiteralPath $racineRendu -Recurse -Force -ErrorAction SilentlyContinue }
}

Write-Host ''
Write-Host "$reussis réussis, $echecs échecs" -ForegroundColor $(if ($echecs -eq 0) { 'Green' } else { 'Red' })
if ($echecs -gt 0) { exit 1 }
