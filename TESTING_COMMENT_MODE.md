# Testing Guide - Comment Mode

## Quick Test (Sin conexión TikTok)

### 1. Configurar modo COMMENT

Edita `src/config.py`:
```python
GAME_MODE = "COMMENT"
```

### 2. Ejecutar sin streamer

```bash
python main.py @test
```

El juego arrancará en modo IDLE mostrando "VOTE IN CHAT TO START!"

### 3. Controles de prueba

Presiona las teclas **1, 2, 3** repetidamente para simular votos:

| Tecla | Acción |
|-------|--------|
| **1** | Voto aleatorio para un país |
| **2** | Voto aleatorio para un país |
| **3** | Voto aleatorio para un país |
| **T** | Regalo pequeño (funciona en ambos modos) |
| **Y** | Regalo grande (funciona en ambos modos) |
| **C** | Reset carrera |

### 4. Qué observar

✅ **Panel de shortcuts** (bottom-left):
- Lista de números 1-12 con siglas
- Colores por país

✅ **Feed de mensajes**:
- `🗳️ TestVoterXXX voted for Argentina`

✅ **Banderas avanzando**:
- Pequeños saltos por cada voto
- Partículas y efectos visuales

✅ **Sistema de capitanes**:
- Nombres de usuarios con más votos
- Puntos totales `@username - (5)`

✅ **Carrera completa**:
- Victoria cuando una bandera llega a meta
- Flash blanco y explosión de confeti
- Leaderboard final con top 3

### 5. Ajustar velocidad

Si la carrera va muy rápido/lento, edita en `src/config.py`:

```python
COMMENT_POINTS_PER_MESSAGE = 1  # Aumentar = más rápido
COMMENT_COOLDOWN = 1.0  # Reducir = más votos permitidos
```

## Test con TikTok Live (simulado)

### Preparación

1. Mantén `GAME_MODE = "COMMENT"`
2. Ejecuta con un streamer real: `python main.py @tu_username`
3. Conéctate desde otro dispositivo al live
4. Escribe en chat: `1`, `arg`, `argentina`, etc.

### Validación

- ✅ Los votos se detectan en consola: `🗳️ @username voted for Argentina`
- ✅ Las banderas avanzan al recibir votos
- ✅ El panel de shortcuts se ve en pantalla
- ✅ El sistema anti-spam funciona (1 voto/segundo por usuario)

## Troubleshooting

**❌ Las teclas 1/2/3 no hacen nada**
- Verifica que `GAME_MODE = "COMMENT"` en config.py
- Revisa los logs en consola

**❌ Las banderas no se ven**
- Fondo oscuro en las banderas: revisar issue de sprites
- Verificar que existan archivos PNG en `assets/gifts/`

**❌ Los votos reales no se detectan**
- Verifica conexión TikTok en logs
- Confirma que el streamer esté en vivo
- Prueba con mensajes exactos: solo `1`, `arg`, etc.

**❌ Carrera va muy lento**
- Aumenta `COMMENT_POINTS_PER_MESSAGE` a 2 o 3
- Reduce `COMMENT_COOLDOWN` a 0.5

**❌ Carrera va muy rápido**
- Reduce `COMMENT_POINTS_PER_MESSAGE` a 0.5
- Aumenta `COMMENT_COOLDOWN` a 2.0

## Comparar con modo GIFT

Para comparar:

1. Cambia `GAME_MODE = "GIFT"` en config.py
2. Ejecuta el juego
3. Presiona **T** o **Y** para regalos de prueba
4. Teclas 1/2/3 ahora activan efectos de combate (Rosa/Pesa/Helado)

## Siguiente paso: Arena Real

Una vez validado en test:
1. Confirma que todo funciona como esperas
2. Prepara OBS con captura de ventana
3. Explica a tu audiencia cómo votar (números o siglas)
4. Inicia stream y observa engagement

**Tip:** Muestra el panel de shortcuts en pantalla para que sepan qué escribir.

---

¿Listo para el ring? 🥊
