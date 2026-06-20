"""Matchup: Argentina vs Brasil — El Clásico Sudamericano."""

from variants.versus.matchups.base import Matchup, TeamDef

ARG_BRA = Matchup(
    id="arg_bra",
    label="🇦🇷 Argentina vs Brasil 🇧🇷",
    left=TeamDef(
        name="Argentina",
        short="ARG",
        color=(116, 172, 223),   # celeste
        accent=(255, 255, 255),
        keywords=["argentina", "arg", "albiceleste", "scaloneta", "a", "1"],
        escudo_path="variants/versus/assets/versus/images/escudo-argentina.png",
        marcador_path="variants/versus/assets/versus/images/marcador-argentina.png",
    ),
    right=TeamDef(
        name="Brasil",
        short="BRA",
        color=(0, 156, 59),     # verde
        accent=(255, 223, 0),   # amarillo
        keywords=["brasil", "brazil", "bra", "canarinha", "verde", "b", "2"],
        escudo_path="variants/versus/assets/versus/images/escudo-brasil.png",
        marcador_path="variants/versus/assets/versus/images/marcador-brasil.png",
    ),
)
