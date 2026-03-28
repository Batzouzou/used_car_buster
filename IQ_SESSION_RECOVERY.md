# TOYOTA iQ — SESSION RECOVERY
**Date:** 2026-03-21  
**Owner:** Jerome Martin — ami cherche Toyota iQ automatique occasion  
**WS-002:** `G:\Downloads\_search_vehicles\` (code) · `G:\Downloads\_search_vehicles\_IQ\` (outputs)  
**Stack:** Python · Claude Sonnet (analyst + pricer) · Ollama/local LLM (fallback cheap tasks)

---

## CONTEXTE

Jerome aide un ami à trouver la meilleure Toyota iQ automatique d'occasion.  
Marché rare : ~60 annonces totales en France, encore moins en automatique.  
Jerome = dev junior / backup / back office. L'ami est l'utilisateur final.

---

## CRITÈRES (VERROUILLÉS)

| Critère | Valeur |
|---------|--------|
| Marque/Modèle | Toyota iQ |
| Transmission | Automatique uniquement (CVT / Multidrive) |
| Budget max | 5 000 € |
| Kilométrage max | 150 000 km |
| Année min | 2009 |
| Zone | France entière, classé par distance Orly (48.7262, 2.3652) |

### Zones de distance
| Zone | Rayon | Bonus scoring |
|------|-------|---------------|
| PRIME | < 20 km | +15 pts |
| NEAR | 20-30 km | +8 pts |
| FAR | 30-40 km | +3 pts |
| REMOTE | > 40 km | 0 |

### Plateformes cibles
| Plateforme | Priorité |
|-----------|----------|
| LeBonCoin | #1 |
| La Centrale | #2 |

Phase 2 (hors scope) : AutoScout24, L'Argus, Le Parking

---

## ARCHITECTURE CIBLE (CORRIGÉE — VRAIMENT AGENTIC)

```
ORCHESTRATOR AGENT (LLM-backed, goal-driven)
    — objectif : trouver les 10 meilleures Toyota iQ auto près Orly < 5k€
    — décide dynamiquement : scraper / analyser / retry / escalader HITL
    — évalue qualité des résultats, adapte stratégie
        ↓
    ┌──────────────┬──────────────┐
SCRAPER AGENT   ANALYST AGENT   PRICER AGENT
(parallel LBC   (score 0-100    (prix marché
+ La Centrale)   prompt contract) + négo messages)
    ↓                ↓               ↓
  Raw JSON      2 shortlists     Nego prompts
  (brut)        pro + particulier  prêts à envoyer
    └────────────────┴───────────────┘
                     ↓
              HITL — Jerome terminal
              + Telegram ami (interface)
              + WhatsApp Jerome (miroir alertes)
                     ↓
              Liste approuvée → Pricer → Outputs
```

---

## INTERFACE UTILISATEUR

### Ami (utilisateur final)
- **Telegram bot** — interface principale
- Commandes simples : lancer recherche, voir shortlist, valider/rejeter annonce
- Bot gère en autonomie, escalade à Jerome si bloqué

### Jerome (back office)
- **Telegram** — miroir alertes techniques + shortlist finale
- **WhatsApp** — notification finale uniquement
- Intervient si : erreur bot, demande hors scope ami, validation technique
- Escalade automatique définie par critères (à spécifier)

---

## PROMPT CONTRACTS (À DÉFINIR)

### Analyst Agent
```
INPUT:  {listing: {titre, prix, km, année, ville, gps, vendeur_type}, criteria: {...}}
OUTPUT: {score: int 0-100, flags: [...], reasoning: str, shortlist: "pro"|"particulier"|"excluded"}
FAILURE: retry si JSON invalide, HALT après 2 échecs
```

### Pricer Agent
```
INPUT:  {listing: {...}, market_data: {...}, approved_by: "jerome"}
OUTPUT: {prix_marche: {min, max}, offre_entree: int, max_acceptable: int, message_nego: str}
FAILURE: retry 2x, flag si pas de données marché réelles
```

---

## DEUX SHORTLISTS SÉPARÉES

- **a) Professionnels** — garages, concessionnaires, mandataires
- **b) Particuliers** — vendeurs privés

Jerome les revoit séparément. Chaque liste classée indépendamment.

---

## FICHIERS DE SORTIE (`G:\Downloads\_search_vehicles\_IQ\`)

| Fichier | Contenu |
|---------|---------|
| `raw_listings_YYYYMMDD.json` | Toutes annonces brutes |
| `shortlist_pro_YYYYMMDD.json` | Top N professionnels |
| `shortlist_part_YYYYMMDD.json` | Top N particuliers |
| `shortlist_approved_YYYYMMDD.json` | Liste approuvée Jerome |
| `priced_YYYYMMDD.json` | Avec analyse prix marché |
| `nego_prompts_YYYYMMDD.txt` | Messages négociation prêts à envoyer |

---

## MODULES

| Fichier | Rôle | LLM ? |
|---------|------|-------|
| `config.py` | Critères, constantes, clés API (.env) | Non |
| `utils.py` | Haversine, geocoding (cache + Nominatim), nettoyage | Non |
| `scraper.py` | LBC + La Centrale en **parallèle** (asyncio) | Non |
| `analyst.py` | Prompt contract → Claude Sonnet → 2 shortlists | Oui |
| `pricer.py` | Prompt contract → Claude Sonnet → prix + négo | Oui |
| `orchestrator.py` | **Agent LLM** goal-driven, pas state machine | Oui |
| `run.py` | CLI entry point | Non |

---

## POINTS CRITIQUES À CORRIGER VS PLAN INITIAL

| Problème | Correction |
|----------|------------|
| State machine ≠ agent | Orchestrateur LLM-backed avec décisions dynamiques |
| Scrape séquentiel | Parallèle asyncio (LBC + La Centrale simultané) |
| Cache 24h trop long | Cache max 4h (marché de 60 annonces, très volatile) |
| Prompt contracts absents | Définis explicitement (input/output/failure) |
| Pricer sans données marché | Injecter données réelles ou flaguer hallucination |
| API keys dans config.py | `.env` + `python-dotenv` obligatoire |
| Zéro observabilité | Logs structurés + trace décisions agent |
| Telegram ami non spécifié | Interface définie, escalade Jerome automatique |

---

## LLM ROUTING

| Tâche | Modèle | Raison |
|-------|--------|--------|
| Scoring annonces | Claude Sonnet | Précision requise |
| Génération messages négo | Claude Sonnet | Qualité rédaction |
| Classification simple (pro/particulier) | Ollama local (Llama) | Cheap, rapide |
| Orchestration | Claude Sonnet | Décisions complexes |

---

## NÉGOCIATION — FEATURE CLÉS

Par annonce approuvée :
- Points d'ancrage négatifs spécifiques au véhicule (kilométrage, historique, usure)
- Nb de propriétaires précédents (usage commercial GA/Uber = flag rouge)
- Message d'attaque en français, vouvoiement, informé, pas insultant
- Version orale + version digitale (tous supports)

---

## NEXT ACTIONS

1. Réécrire `orchestrator.py` comme vrai agent LLM (goal-driven, tool calls)
2. Définir prompt contracts complets analyst + pricer
3. Implémenter scraper parallèle (asyncio)
4. Configurer `.env` sécurisé
5. Spécifier interface Telegram ami + miroir Jerome
6. Ajouter logs structurés + trace décisions

---

## COMMANDES CLI

```bash
python run.py           # Pipeline complet
python run.py scrape    # Scrape uniquement
python run.py analyze   # Analyser dernier scrape
python run.py price     # Pricer dernière shortlist approuvée
```
