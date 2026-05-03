"""Matchup: River Plate vs Boca Juniors — El Superclásico."""

from variants.versus.matchups.base import Matchup, TeamDef

RIVER_BOCA = Matchup(
    id="river_boca",
    label="⚽ Superclásico — River vs Boca",
    left=TeamDef(
        name="River",
        short="RIV",
        color=(255, 255, 255),
        accent=(220, 40, 40),
        keywords=["river", "riv", "millo", "millonario", "rvr", "r", "1"],
        escudo_path="assets/versus/images/escudo-river.png",
        marcador_path="assets/versus/images/marcador-river.png",
    ),
    right=TeamDef(
        name="Boca",
        short="BOC",
        color=(0, 80, 200),
        accent=(255, 215, 0),
        keywords=["boca", "boc", "xeneize", "boquense", "b", "2"],
        escudo_path="assets/versus/images/escudo-boca.png",
        marcador_path="assets/versus/images/marcador-boca.png",
    ),
    gift_team_map={
        "rosquilla": "River",
        "doughnut":  "River",
        "dona":      "River",
        "capibara":  "Boca",
        "capybara":  "Boca",
    },
)
