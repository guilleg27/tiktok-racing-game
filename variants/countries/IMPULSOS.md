# Countries variant — Tabla de impulsos

**Pista: 322 px · Fórmula base: `diamond_count × 3.0 px × 0.33 (gift scale)`**

---

## Votos (COMMENT mode)

| Input | Distancia neta |
|-------|----------------|
| Comentario válido | **0.36 px** · cooldown 1s/usuario |

---

## Eventos sociales

| Evento | Distancia | Cooldown |
|--------|-----------|----------|
| Share | **3 px** | 3s/usuario |
| Follow | **15 px** | ninguno |
| Quiereme (regalo) | **45 px** | ninguno |

---

## Gifts (diamond × 3.0 × 0.33 = diamond × 0.99 px)

| Regalo | Diamantes | Distancia neta | Equivale a N votos |
|--------|-----------|----------------|--------------------|
| Rosa / Helado | 1💎 | **0.99 px** | ~2.75 votos |
| Corazón | 5💎 | **4.95 px** | ~14 votos |
| Perfume / Pesas | 10💎 | **9.9 px** | ~27 votos |
| Drama Queen | 25💎 | **24.75 px** | ~69 votos |
| Dona | 50💎 | **49.5 px** | ~138 votos |
| León | 100💎 | **99 px** → surge 80 + ~6s drain | ~275 votos |
| Capibara | ~299💎 | **~296 px** → surge 80 + ~72s drain | ~822 votos |

> Gifts con distancia > 80 px activan el overflow drain (ver sección abajo).

**Efectos de combate** (escalados 0.33× sobre los valores del core):

| Regalo | Efecto original | Efecto Countries |
|--------|----------------|-----------------|
| Rosa combat | +5 px | **+1.65 px** al país sender |
| Pesa combat | +10 px | **+3.3 px** al país sender |
| Helado | Freeze 5s al líder | sin cambio |

---

## Sistema de overflow (anti-teletransporte)

Cuando `target_x` supera en más de **80 px** la posición física del corredor, el exceso se encola y drena a **3 px/s**.

| Burst | Distancia neta | Surge inmediato | Drain |
|-------|---------------|-----------------|-------|
| 100 Rosas (33 px) | 33 px | 33 px directo | sin overflow |
| Dona (49.5 px) | 49.5 px | 49.5 px directo | sin overflow |
| León (99 px) | 99 px | 80 px surge | ~6s drain |
| Burst 243💎 (~240 px) | ~240 px | 80 px surge | ~53s drain |

---

## Combos / Multiplicadores

| Sistema | Threshold | Efecto en distancia |
|---------|-----------|---------------------|
| COMBO general | 3 gifts en 5s | Solo visual/audio — sin bonus de distancia |
| ON FIRE | 10 gifts en 5s | Solo visual/trails — sin bonus de distancia |
| Rosa combo L1 | 3 Rosas en 2s | ×1.2 a todos los impulsos mientras activo |
| Rosa combo L2 | 6 Rosas en 2s | ×1.5 a todos los impulsos mientras activo |
| Rosa combo L3 | 10 Rosas en 2s | ×2.0 a todos los impulsos mientras activo |
| Hype mode | likes goal | ×1.15 a todos los impulsos mientras activo |

> Rosa combo L3 + Hype mode = ×2.0 × ×1.15 = **×2.3 máximo**
> Nota: estos multiplicadores se aplican ANTES del gift scale 0.33×.

---

## Autopilot (inactividad >45s)

| Target | Distancia promedio | Frecuencia |
|--------|-------------------|------------|
| Normal (2-4 países) | ~90 px/evento | cada ~5s |
| Final target | ~240 px/evento | por evento |

> El autopilot usa `apply_gift_impulse` directamente, por lo que **no** pasa por el gift scale 0.33×.
> Se pausa 20s tras cualquier actividad real.

---

## Tiempos de carrera estimados

| Viewers | Participantes (50%) | País líder | Tiempo solo votos |
|---------|---------------------|------------|-------------------|
| 10–15 | 5–7 | 1–2 voters | ~640s (autopilot compensa) |
| 30–50 | 15–25 | 3–4 voters | ~230s (~3.8 min) |
| 80–100 | 40–50 | 5–7 voters | ~130–184s (~2–3 min) |
| 150 (boost) | 75 | 8–12 voters | ~77–115s (~1.5–2 min) |

---

## Constantes en código (`variants/countries/game_engine.py`)

| Constante | Valor | Descripción |
|-----------|-------|-------------|
| `_COUNTRIES_VOTE_DIAMOND` | 0.12 | diamond_count por voto → 0.36 px |
| `_COUNTRIES_GIFT_SCALE` | 0.33 | multiplicador sobre distancia de gifts |
| `_COUNTRIES_MAX_TARGET_LEAD` | 80.0 px | cap del overflow drain |
| `_COUNTRIES_DRAIN_RATE` | 3.0 px/s | velocidad de drenado del overflow |
| `_COUNTRIES_SHARE_DISTANCE` | 1 | → 3 px por share |
| `_COUNTRIES_SHARE_COOLDOWN` | 3.0s | cooldown entre shares del mismo usuario |
| `_COUNTRIES_FOLLOW_DISTANCE` | 5 | → 15 px por follow |
| `_COUNTRIES_QUIEREME_DISTANCE` | 15 | → 45 px por regalo Quiereme |

---

*Archivo generado desde `variants/countries/game_engine.py`*
