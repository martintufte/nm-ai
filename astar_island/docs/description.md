# Task 2: Astar Island - Norse World Prediction

## Overview

Observe a black-box Norse civilization simulator via limited viewports and predict final terrain
probability distributions on a 40x40 grid.

## Simulation

- 40x40 cell map, simulation runs 50-year cycles
- Phases each year: Growth → Conflict → Trade → Winter → Environment
- Query budget: **50 queries per round**, shared across 5 random seeds (~10 per seed)
- Each query reveals a **15x15 viewport**

## Terrain Classes (6 prediction classes)

| Class | Terrain | Notes |
| ----- | ------- | ----- |
| 0 | Ocean/Plains/Empty | Static |
| 1 | Settlement | Dynamic |
| 2 | Port | Coastal settlements |
| 3 | Ruin | Collapsed settlements |
| 4 | Forest | Reclaims abandoned land |
| 5 | Mountain | Permanent |

## API

Base URL: `api.ainm.no/astar-island/`

| Endpoint | Method | Description |
| -------- | ------ | ----------- |
| `/rounds` | GET | List active rounds |
| `/rounds/{round_id}` | GET | Round details + initial map states |
| `/budget` | GET | Remaining queries |
| `/simulate` | POST | Query viewport (costs 1 query) |
| `/submit` | POST | Submit predictions |
| `/my-rounds` | GET | Team-specific data |
| `/my-predictions/{round_id}` | GET | Retrieved submitted predictions |
| `/analysis/{round_id}/{seed_index}` | GET | Post-round ground truth |
| `/leaderboard` | GET | Public standings |

## Authentication

Cookie `access_token` (JWT) or `Authorization: Bearer <token>`

## Prediction Format

3D array `[40][40][6]`. Each cell's 6 probabilities must sum to 1.0 (±0.01 tolerance).

**CRITICAL**: Never assign 0.0 probability to any class. Use minimum floor of 0.01, then renormalize.

## Scoring

- Entropy-weighted KL divergence: `KL(p||q) = Σ p_i * log(p_i / q_i)`
- Only dynamic cells contribute, weighted by entropy
- Scale: 100 = perfect, 0 = terrible
- Round score = average of 5 seed scores
- Leaderboard = best round score (later rounds may have higher weights)
