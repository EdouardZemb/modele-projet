<#
    Tester-Nouveau-Projet.ps1 — tests de Nouveau-Projet.ps1.
    Ne crée rien de réel : l'index est une copie temporaire, -ABlanc ne fait que lire.
    Usage : powershell -NoProfile -ExecutionPolicy Bypass -File .\Tester-Nouveau-Projet.ps1
#>
$ErrorActionPreference = 'Stop'
$ici     = Split-Path -Parent $MyInvocation.MyCommand.Path
$script  = Join-Path $ici 'Nouveau-Projet.ps1'
$indexReel = Join-Path $HOME 'Documents\INDEX-PROJETS.md'
$echecs  = 0
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

# ------------------------------------------------------------ encodage du script
Write-Host 'Encodage'
$octets = if (Test-Path $script) { [IO.File]::ReadAllBytes($script) } else { @() }
Verifier 'Nouveau-Projet.ps1 commence par EF BB BF' ($octets.Length -ge 3 -and $octets[0] -eq 0xEF -and $octets[1] -eq 0xBB -and $octets[2] -eq 0xBF)

# ------------------------------------------------------------ nom invalide
Write-Host 'Nom invalide'
$sortie = Lancer-Enfant @('-Nom', 'Mauvais_Nom', '-Description', 'x', '-ABlanc')
Verifier 'le message contient « minuscules »' ($sortie -match 'minuscules') $sortie
Verifier 'aucune étape n''a commencé' ($sortie -notmatch 'préalables') $sortie

# ------------------------------------------------------------ à blanc
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

# ------------------------------------------------------------ fonctions, par point-source
Write-Host 'Fonctions'
. $script -Nom 'essai-fonctions' -Description 'Essai' -Version 'v0.1.0'
Verifier 'Get-LigneIndex est chargée' ($null -ne (Get-Command Get-LigneIndex -ErrorAction SilentlyContinue))
Verifier 'Add-LigneIndex est chargée' ($null -ne (Get-Command Add-LigneIndex -ErrorAction SilentlyContinue))
Verifier 'Get-Etapes est chargée'     ($null -ne (Get-Command Get-Etapes -ErrorAction SilentlyContinue))

if ((Get-Command Get-LigneIndex -ErrorAction SilentlyContinue) -and (Get-Command Add-LigneIndex -ErrorAction SilentlyContinue)) {
    $ligne = Get-LigneIndex -Nom 'essai-fonctions' -Version 'v0.1.0' -Visibilite 'public' -Date '2026-10-16'
    Verifier 'ligne publique : gabarit' ($ligne -eq '| essai-fonctions | code | `C:\src\github.com\EdouardZemb\essai-fonctions` — né de modele-projet v0.1.0 le 2026-10-16 | EdouardZemb/essai-fonctions | OUI | 2026-10-16 |') $ligne
    $lignePrive = Get-LigneIndex -Nom 'essai-fonctions' -Version 'v0.1.0' -Visibilite 'prive' -Date '2026-10-16'
    Verifier 'ligne privée : mention (privé)' ($lignePrive -match '\(privé\)') $lignePrive
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
        Copy-Item $indexReel $tmp
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

if (Get-Command Get-Etapes -ErrorAction SilentlyContinue) {
    $etapes = @(Get-Etapes)
    Verifier 'Get-Etapes rend onze étapes' ($etapes.Count -eq 11) "$($etapes.Count)"
    Verifier 'chaque étape a Description, Commande, Action' (@($etapes | Where-Object { $_.Description -and $_.Commande -and $_.Action }).Count -eq $etapes.Count)

    # Une action ne voit que le contexte recopié par Import-Ctx : toute variable qu'elle lit
    # sans l'affecter elle-même doit y figurer (le 17/10, « mdl » manquait : copier a reçu « gh: »).
    $automatiques = @('true', 'false', 'null', 'HOME', 'Matches', '_', 'LASTEXITCODE')
    $absentes = @()
    for ($n = 0; $n -lt $etapes.Count; $n++) {
        $ast = $etapes[$n].Action.Ast
        $affectees = @($ast.FindAll({ $args[0] -is [System.Management.Automation.Language.AssignmentStatementAst] }, $true) |
            Where-Object { $_.Left -is [System.Management.Automation.Language.VariableExpressionAst] } |
            ForEach-Object { $_.Left.VariablePath.UserPath })
        $lues = @($ast.FindAll({ $args[0] -is [System.Management.Automation.Language.VariableExpressionAst] }, $true) |
            ForEach-Object { $_.VariablePath.UserPath } | Sort-Object -Unique)
        foreach ($v in $lues) {
            if ($v -notin $affectees -and $v -notin $automatiques -and -not $script:Ctx.ContainsKey($v)) {
                $absentes += "étape $($n + 1) : `$$v"
            }
        }
    }
    Verifier 'chaque variable lue par une action est dans le contexte' ($absentes.Count -eq 0) ($absentes -join ', ')
    Verifier 'le contexte nomme le modèle EdouardZemb/modele-projet' ($script:Ctx['mdl'] -eq 'EdouardZemb/modele-projet') "$($script:Ctx['mdl'])"
}

# ------------------------------------------------------------ rendu réel de la fusion
# Seule l'étape « copier copy » est exécutée, dans un dossier temporaire ; rien ne part sur GitHub.
# v0.1.0 n'a pas la question « fusion » : on rend v0.2.0, la première version qui l'a.
Write-Host 'Rendu de la fusion (copier copy seul, dossier temporaire)'
$racineRendu = Join-Path ([IO.Path]::GetTempPath()) ("rendu-fusion-{0}" -f [guid]::NewGuid())
try {
    foreach ($cas in @(@{ Nom = 'essai-fusion-edouard'; Args = @{ Fusion = 'edouard' }; Attendu = 'edouard' },
                       @{ Nom = 'essai-fusion-defaut';  Args = @{};                    Attendu = 'session' })) {
        $argsCas = $cas.Args
        . $script -Nom $cas.Nom -Description 'Essai' -Version 'v0.2.0' -RacineCode $racineRendu @argsCas
        $etapesRendu = @(Get-Etapes)
        $erreurRendu = $null
        try { & $etapesRendu[1].Action } catch { $erreurRendu = $_.Exception.Message }
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
