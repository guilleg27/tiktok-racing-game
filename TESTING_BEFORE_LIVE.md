# 🧪 Testing Before Going LIVE

Guía para probar el juego **sin conectar a TikTok** antes de ir en vivo.

---

## 1. Arrancar en modo IDLE (sin TikTok)

```bash
python main.py --idle
```

o

```bash
python main.py -i
```

Se abre la ventana en estado **IDLE**. No hay conexión a TikTok. Puedes probar todo con teclas.

---

## 2. Controles de prueba

| Tecla | Acción | Qué prueba |
|-------|--------|------------|
| **T** | Regalo pequeño aleatorio | SFX pequeño, movimiento, partículas |
| **Y** | Regalo grande aleatorio | SFX grande, movimiento, partículas |
| **1** | Voto país 1 (COMMENT) / Rosa (GIFT) | Votos, combo, SFX vote |
| **2** | Voto país 2 (COMMENT) / Pesa (GIFT) | Votos, combo, efecto Pesa |
| **3** | Voto país 3 (COMMENT) / Helado (GIFT) | Votos, combo, efecto Helado |
| **J** | Usuario se une a equipo | Join, asignación de país |
| **K** | Puntos de capitán aleatorios | Sistema de capitanes |
| **F** | Combo rápido → ON FIRE | Combo fire SFX, TTS "X is on fire!" |
| **G** | Activar Final Stretch | Sirena, warp mode, TTS final stretch |
| **V** | Secuencia de victoria | Victory SFX, TTS ganador, confetti |
| **C** o **R** | Reset carrera → IDLE | Volver a pantalla inicial |
| **L** | Conectar a TikTok | Pedir username y conectar (cuando quieras ir LIVE) |
| **ESC** | Salir | Cerrar juego |

---

## 3. Flujo recomendado (simular una carrera)

1. **Arrancar:** `python main.py --idle`
2. **Iniciar carrera:** Pulsa **T** o **Y** → pasa de IDLE a RACING.
3. **Votar:** Pulsa **1**, **2**, **3** muchas veces (países distintos) → votos, combos, SFX.
4. **Combo ON FIRE:** Pulsa **F** → combo rápido, SFX fuego, TTS "X is on fire!".
5. **Final stretch:** Pulsa **G** → sirena, fondo warp, TTS "Final stretch! X is in the lead!".
6. **Victoria:** Pulsa **V** → ganador aleatorio, fanfarria, TTS "X wins the race!", confetti.
7. **Reset:** Pulsa **C** → vuelve a IDLE. Repite 2–6 las veces que quieras.

---

## 4. Probar solo audio

```bash
python test_audio.py
```

Comprueba BGM, SFX (gift, vote, combo, final stretch, victory, freeze) y, si instalas pyttsx3, TTS.

---

## 5. Probar voces TTS

```bash
python list_voices.py
```

Lista voces disponibles y permite probarlas. Útil para elegir voz antes de ir LIVE.

---

## 6. Conectar a TikTok (ir LIVE)

Cuando hayas probado todo:

1. Con el juego en IDLE, pulsa **L**.
2. Escribe el **@username** del streamer y Enter.
3. Se conecta a TikTok Live y empiezan a llegar votos/regalos reales.

O arrancar ya conectado:

```bash
python main.py @streamer_username
```

---

## 7. Checklist pre-LIVE

- [ ] `python main.py --idle` abre bien y ves la pantalla IDLE.
- [ ] **T** / **Y** inician carrera y se escuchan SFX de regalos.
- [ ] **1** / **2** / **3** generan votos y SFX (y combos si votas rápido).
- [ ] **F** activa ON FIRE y suena combo fire + TTS.
- [ ] **G** activa Final Stretch (sirena + warp + TTS).
- [ ] **V** dispara victoria (fanfarria + TTS + confetti).
- [ ] **C** resetea a IDLE correctamente.
- [ ] Volumen del sistema adecuado y sin errores en consola.
- [ ] Si usas OBS: probar captura de ventana y croma.

---

## 8. Modo COMMENT vs GIFT

En `src/config.py`:

```python
GAME_MODE = "COMMENT"  # votos por chat (1, 2, arg, bra...)
# GAME_MODE = "GIFT"   # regalos de TikTok
```

Prueba en **COMMENT** con **1** / **2** / **3** para simular votos. En **GIFT**, **1** / **2** / **3** activan Rosa / Pesa / Helado.

Ver [COMMENT_MODE.md](COMMENT_MODE.md) para más detalles.
