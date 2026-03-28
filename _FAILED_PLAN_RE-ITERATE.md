# Toyota iQ Auto — Car Search Pipeline

## Contexte
Jerome aide un ami à rechercher la meilleure **Toyota IQ*** compte tenu des spécifications et ontraites de cet ami.

Cette **Toyota IQ** devra:
-être automatique-Marché de l'occasion,
-boîte automatique d'occasion pour usage personnel. 
-etre visible dans de 20 km autour d'Orly.

Cet Agent agantiques :
Permettre de passer en revue l'intégralité des véhicules en vente sur le marché de l'occasuions dans le périmètre défini.
Ensuite des les analyzer , le spasser dans un barème d enotzatin et d ehor tlist of 10 thaat are the *best fit* in regards to friends requests, contraibnts §...
Agent must cross analyze obvious criterion that maques a car better than another , cross checking ideal carf for friend 👉🏻 shortlist (10 so far)

Modèle rare en France (~60 annonces totales, encore moins en automatique). Besoin d'un outil qui scrape exhaustivement les principales plateformes, analyse les offres, et produite uine shotlist d e10.

Dans un autre temps une feazture: uggérer rquelques points (ancrages) à utuliser fonction de chaque vévicule (les COn4s du vehicle) afin de négocier le prix 'achat à la baisqse.et prépare la négociation.

👉🏻 suggérer des phrase bie construites prête sà entre envoyéd (digital)tous supports) 
ou bien utilisées à l'oral.

## Objectif
Pipeline local (WS-002) en 4 étapes : scraper → analyser → valider (Jerome) → pricer + négocier.

******************** VALIDER QUOI".

## Dossiers
- **Code source :** `G:\Downloads\_search_vehicles\` (dossier de travail exclusif)
- **Sorties (données) :** `G:\Downloads\_search_vehicles\_IQ\`
- **Master files :** `C:\Users\jerome\.claude\projects\X---My-Gateway-Premium\memory\` (comme tous les projets)

---

## Cahier des charges

### Critères de recherche (verrouillés)
| Critère | Valeur |
|---------|--------|
| Marque/Modèle | Toyota iQ |
| Transmission | **Automatique uniquement** (CVT / Multidrive) |
| Budget max | 5 000 € |
| Kilométrage max | 150 000 km |
| Année min | 2009 |
| Zone de recherche | France entière, classé par distance d'Orly |

Maintenance anciens proprios
combien differents proprio
activités commercial véhicule GA/UIBER/ zrc zrcAGENTIQUIE IS suppose dto K?NOW :

### Zones de distance (depuis Orly — 48.7262, 2.3652)
| Zone | Rayon | Bonus scoring |
|------|-------|---------------|
| PRIME | < 20 km | +15 pts |
| NEAR | 20-30 km | +8 pts |
| FAR | 30-40 km | +3 pts |
| REMOTE | > 40 km | 0 |

### Plateformes cibles
| Plateforme | Priorité | Type vendeur | Approche technique |
|-----------|----------|--------------|-------------------|
| LeBonCoin | #1 | Mixte (pro + particulier) | API interne JSON ou HTML fallback |
| La Centrale | #2 | Pro-dominant | HTML parsing |

Phase 2 (hors scope) : AutoScout24, L'Argus (référence prix), Le Parking (agrégateur)

### Deux shortlists séparées
L'analyse produit **deux listes indépendantes** :
- **a) Professionnels** — garages, concessionnaires, mandataires
- **b) Particuliers** — vendeurs privés

Jerome les revoit séparément. Chaque liste a son propre classement.

---

## Architecture

### Pipeline (4 étapes + orchestrateur)

```
[ORCHESTRATEUR] — state machine, retry, fallback, détection données périmées
    │
    ├─[1] SCRAPER
    │     LeBonCoin + La Centrale → JSON brut (titre, prix, km, année, lieu, GPS, type vendeur)
    │
    ├─[2] ANALYST (agent LLM — Claude Sonnet)
    │     Évalue chaque annonce → score 0-100 → 2 shortlists (pro + particulier)
    │     Critères : prix vs marché, km, année, proximité Orly, état, confirmation auto
    │     Drapeaux rouges : manuelle, >5000€, >150k km, "en l'état", accident
    │
    ├─[3] HITL (Jerome en terminal)
    │     Revoit les 2 listes → ok / drop / top N / rescrape / quit
    │     Validation → merge + sauvegarde liste approuvée
    │
    └─[4] PRICER (agent LLM — Claude Sonnet)
          Par annonce approuvée :
          - Prix marché (fourchette basse/haute)
          - Offre d'entrée + max acceptable (négo)
          - Message d'attaque en français (vouvoiement, informé, pas insultant)
```
Pondérer avec éléme,nt sdivers comme kilométrage élévé, trioop éléve / cartégories, rayure scarrosserueszembe etre sortue du SIC =V ??? (agentique does not nee dme to dradft all possibilités)
### Orchestrateur — state machine

```
INIT → SCRAPE → VALIDATE → ANALYZE → HITL → PRICE → DONE
                   │                    │
                   ↓ (0 annonces)       ↓ (parse fail)
               RETRY_SCRAPE         RETRY_ANALYZE
                   │ (max 2x)          │ (max 2x)
                   ↓                   ↓
                 FAILED              FAILED
```

Décisions automatiques :
- Données <24h en cache ? → skip scrape, aller direct à VALIDATE
- 1 plateforme KO, l'autre OK ? → continuer avec les données partielles
- LLM retourne du garbage ? → retry 2x, puis FAILED
- Jerome tape `rescrape` dans HITL ? → retour à SCRAPE
- Jerome tape `top 20` ? → retour à ANALYZE avec nouveau N

### Modules

| Fichier | Responsabilité | Appelle un LLM ? |
|---------|---------------|-------------------|
| `config.py` | Critères, constantes, clés API, zones distance | Non |
| `utils.py` | Haversine, geocoding (cache + Nominatim), nettoyage texte | Non |
| `scraper.py` | 2 scrapers (LBC API+fallback, La Centrale HTML) | Non |
| `analyst.py` | Prompt analyst → Claude → 2 shortlists scorées | Oui (Claude Sonnet) |
| `pricer.py` | Prompt pricer → Claude → prix marché + message négo | Oui (Claude Sonnet) |
| `orchestrator.py` | State machine, retry, fallback, HITL loop | Non |
| `run.py` | CLI entry point (thin wrapper) | Non |

### Fichiers de sortie (`G:\Downloads\_search_vehicles\_IQ\`)

| Fichier | Contenu |
|---------|---------|
| `raw_listings_YYYYMMDD.json` | Toutes les annonces brutes |
| `shortlist_pro_YYYYMMDD.json` | Top N professionnels |
| `shortlist_part_YYYYMMDD.json` | Top N particuliers |
| `shortlist_approved_YYYYMMDD.json` | Liste approuvée par Jerome (merged) |
| `priced_YYYYMMDD.json` | Avec analyse prix marché |
| `nego_prompts_YYYYMMDD.txt` | Messages de négociation prêts à envoyer |

Ami a un BOT Telegram installé récemment (projet POOL)
Jérôme en mirroir mais ami doi tinterrager priçncipalement  jérome fall bodown/dev/technique/orienta ami si difficultesd /perdu abvec BOT.
---

## Geocoding

Problème : La Centrale ne fournit pas de coordonnées GPS, juste un nom de ville.
Solution : cache local des 20 principales villes IDF + fallback Nominatim (gratuit, OpenStreetMap).

---

## Tests

- Tests unitaires avec **mocks Claude API** (pas d'appels réels en test)
- Fixtures : HTML La Centrale + JSON LeBonCoin capturés manuellement
- `conftest.py` pour les imports Windows
- Tests orchestrateur : couverture des transitions d'état

---

## Dépendances

- `requests` (déjà dispo)
- `beautifulsoup4` (à installer)
- `anthropic` (à installer)

---

## Commandes CLI

```
python run.py           # Pipeline complet
python run.py scrape    # Scrape uniquement
python run.py analyze   # Analyser le dernier scrape
python run.py price     # Pricer la dernière shortlist approuvée
```

---

## Risques et mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| LBC bloque l'API | Pas d'annonces LBC | Fallback HTML (__NEXT_DATA__) |
| La Centrale change son HTML | Parser cassé | Fixtures + tests, ajustement sélecteurs |
| 0 annonces Toyota iQ auto | Pipeline vide | Le marché est petit, c'est normal certains jours |
| Claude retourne du JSON invalide | Analyse échoue | Retry 2x + extraction JSON robuste |
| Geocoding Nominatim down | Distance = REMOTE pour La Centrale | Cache local 20 villes couvre 80% des cas |

---

## Hors scope (Phase 2)

- Alertes Telegram pour nouvelles annonces
- AutoScout24 / L'Argus / Le Parking
- Historique prix (tracking changements)
- Déploiement VPS (scheduled daily)
- Suivi des annonces déjà contactées


GROS SOUCI 5ROLL AGAI EXTRRABALL°§
NOT AGENTIC
HOW FOEAS YOU R FLOW AGEN?T WORKS?. PAALLE/in/out
Son,otet cheap enough for thzt small modrl top be  Fall bqck LM areena and probably Lama as a mutiple local LLM's intefacez/server./


Ollamaq
Local AI

WS-002 shal soon receive an extra 32 GB therefore 64 GB more cofortable a   nd far from overflow lik;e now with 32 GB RAM. 


NO AGENT C ONTROLING YOU AS THIS PLAN IMPLEMENTER AT ALL §§ MAJOR ISSUE

NO AGENT CONTROLLING THE AGENTIC 5WELKL THAT ITS NAME ACVTUALKL YIT IS NOT //°.

FAILED REITERAT/use proper skills not on,kly to write but to be safe/security/compliance/best pracvtices :====µ> GOT ME?


No Agentiques prompts??

