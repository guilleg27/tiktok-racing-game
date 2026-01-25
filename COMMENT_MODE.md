# Comment Mode - Interactive Chat Racing

## Overview

The game now supports two modes:
- **GIFT Mode** (original): Players send TikTok gifts to make countries advance
- **COMMENT Mode** (new): Players type shortcuts in chat to vote for countries

## How to Switch Modes

Edit `src/config.py`:

```python
# Change this line:
GAME_MODE = "COMMENT"  # or "GIFT"
```

## Comment Mode Features

### Voting System
- Each user votes by typing a **country shortcut** in chat
- Valid shortcuts:
  - **Numbers**: `1` to `12` (one per country)
  - **Siglas**: `ARG`, `BRA`, `MEX`, `ESP`, `COL`, `CHI`, `PER`, `VEN`, `USA`, `IDN`, `RUS`, `ITA`
  - **Full names**: `argentina`, `brasil`, `mexico`, etc.

### Shortcuts Reference

| # | Sigla | Country   | Shortcuts                    |
|---|-------|-----------|------------------------------|
| 1 | ARG   | Argentina | `1`, `arg`, `argentina`      |
| 2 | BRA   | Brasil    | `2`, `bra`, `brasil`, `brazil` |
| 3 | MEX   | Mexico    | `3`, `mex`, `mexico`, `méxico` |
| 4 | ESP   | España    | `4`, `esp`, `españa`, `spain` |
| 5 | COL   | Colombia  | `5`, `col`, `colombia`       |
| 6 | CHI   | Chile     | `6`, `chi`, `chile`          |
| 7 | PER   | Peru      | `7`, `per`, `peru`, `perú`   |
| 8 | VEN   | Venezuela | `8`, `ven`, `venezuela`, `vzla` |
| 9 | USA   | USA       | `9`, `usa`, `us`, `america`  |
| 10| IDN   | Indonesia | `10`, `idn`, `indonesia`, `indo` |
| 11| RUS   | Russia    | `11`, `rus`, `russia`, `ru`  |
| 12| ITA   | Italy     | `12`, `ita`, `italy`, `italia` |

### Visual UI

**Shortcuts Panel** (bottom-left):
- Shows all available shortcuts during the race
- Color-coded by country flag colors
- Updates in real-time

**Idle Screen**:
- Shows "VOTE IN CHAT TO START!" instead of "SEND A ROSE"

**Message Feed**:
- Shows vote events: `🗳️ @username voted for Argentina`

### Configuration

Customize Comment Mode in `src/config.py`:

```python
# Points awarded per valid comment
COMMENT_POINTS_PER_MESSAGE = 1

# Cooldown between votes from same user (seconds)
COMMENT_COOLDOWN = 1.0
```

### Captain System

Works the same as GIFT mode:
- The user with most votes in a country becomes captain
- Captain name and points display next to the flag

### Technical Details

**Event Flow**:
1. User types shortcut in TikTok chat
2. `TikTokManager` detects valid shortcut
3. Creates `EventType.VOTE` event
4. `GameEngine` processes vote and updates race
5. Visual feedback: particles + floating text

**Anti-spam**:
- Users can only vote once per cooldown period (default: 1 second)
- Prevents chat flooding from affecting race balance

## Comparison: GIFT vs COMMENT Mode

| Feature              | GIFT Mode        | COMMENT Mode     |
|---------------------|------------------|------------------|
| **Interaction**     | Send TikTok gifts | Type in chat     |
| **Cost**            | Real money       | Free             |
| **Points**          | Based on diamonds | 1 point per vote |
| **Engagement**      | Monetization     | Participation    |
| **Speed**           | Variable         | Fast (spam-safe) |
| **Best For**        | Streamers earning | Community events |

## Tips for Streamers

### For COMMENT Mode:
- Encourage viewers to spam their country number/sigla
- Create team rivalries in chat
- Use as warm-up before switching to GIFT mode
- Great for viewers who can't afford gifts

### For GIFT Mode:
- Reward top gifters with shoutouts
- Show captain leaderboard
- Use combat items (Rosa, Pesa, Helado) for strategy

## Troubleshooting

**Votes not registering?**
- Check that `GAME_MODE = "COMMENT"` in `src/config.py`
- Verify shortcuts are typed exactly (case-insensitive)
- Check cooldown settings

**Race starting too fast?**
- Increase `COMMENT_COOLDOWN` to slow down voting

**Want both modes active?**
- Not currently supported (would require code changes)
- Choose one mode per stream session

---

**Version**: 2.0  
**Last Updated**: 2026-01-25
