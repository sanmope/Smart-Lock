import math
import random
from typing import Tuple, List, Dict


# ---------------------------------------------------------------------------
# GPS routes across Argentina — each is a list of (latitude, longitude) waypoints
# ---------------------------------------------------------------------------

BA_MENDOZA: List[Tuple[float, float]] = [
    (-34.6037, -58.3816),   # Buenos Aires
    (-34.5706, -59.1100),   # Lujan
    (-34.6513, -59.4307),   # Mercedes
    (-34.5933, -60.9467),   # Junin
    (-34.2682, -62.2932),   # Rufino
    (-34.1272, -63.3922),   # Laboulaye
    (-33.6760, -65.4604),   # Villa Mercedes
    (-33.3017, -66.3378),   # San Luis
    (-33.0456, -67.5212),   # Desaguadero
    (-33.3100, -67.9600),   # La Paz
    (-33.2965, -68.3307),   # San Martin
    (-32.8895, -68.8458),   # Mendoza
]

BA_ROSARIO: List[Tuple[float, float]] = [
    (-34.6037, -58.3816),   # Buenos Aires
    (-34.0981, -59.0286),   # Zarate
    (-33.3361, -60.2261),   # San Nicolas
    (-33.0078, -60.5396),   # Villa Constitucion
    (-32.9468, -60.6393),   # Rosario
]

BA_CORDOBA: List[Tuple[float, float]] = [
    (-34.6037, -58.3816),   # Buenos Aires
    (-34.0981, -59.0286),   # Zarate
    (-33.8900, -60.5700),   # Pergamino
    (-33.7456, -61.9688),   # Venado Tuerto
    (-32.6283, -62.6803),   # Bell Ville
    (-32.0500, -63.4500),   # Rio Tercero
    (-31.4201, -64.1888),   # Cordoba
]

BA_MAR_DEL_PLATA: List[Tuple[float, float]] = [
    (-34.6037, -58.3816),   # Buenos Aires
    (-35.5725, -58.0106),   # Chascomus
    (-36.3132, -57.6789),   # Dolores
    (-36.8693, -57.7300),   # Mar de Ajo
    (-37.3260, -57.7200),   # Pinamar
    (-37.6733, -57.5500),   # Villa Gesell
    (-38.0055, -57.5426),   # Mar del Plata
]

ROSARIO_TUCUMAN: List[Tuple[float, float]] = [
    (-32.9468, -60.6393),   # Rosario
    (-31.6107, -60.6973),   # Santa Fe
    (-30.9500, -60.7700),   # San Justo
    (-29.9069, -61.9517),   # Ceres
    (-29.2311, -63.0136),   # Anatuya
    (-27.7834, -64.2642),   # Santiago del Estero
    (-27.1200, -65.0400),   # Monteros
    (-26.8083, -65.2176),   # Tucuman
]

URBAN_BA: List[Tuple[float, float]] = [
    (-34.6037, -58.3816),   # Centro
    (-34.5553, -58.4568),   # Palermo
    (-34.4750, -58.5100),   # Vicente Lopez
    (-34.4561, -58.5733),   # San Isidro
    (-34.5320, -58.5570),   # Caseros
    (-34.6345, -58.4008),   # Barracas
    (-34.6037, -58.3816),   # Centro (loop)
]


ROUTES: Dict[str, List[Tuple[float, float]]] = {
    "BA_MENDOZA": BA_MENDOZA,
    "BA_ROSARIO": BA_ROSARIO,
    "BA_CORDOBA": BA_CORDOBA,
    "BA_MAR_DEL_PLATA": BA_MAR_DEL_PLATA,
    "ROSARIO_TUCUMAN": ROSARIO_TUCUMAN,
    "URBAN_BA": URBAN_BA,
}


def get_random_route() -> str:
    """Return a random route name."""
    return random.choice(list(ROUTES.keys()))


def _segment_lengths(route: List[Tuple[float, float]]) -> List[float]:
    """Compute the Euclidean distance of each segment in the route."""
    lengths = []
    for i in range(len(route) - 1):
        dy = route[i + 1][0] - route[i][0]
        dx = route[i + 1][1] - route[i][1]
        lengths.append(math.sqrt(dy * dy + dx * dx))
    return lengths


def interpolate(
    route: List[Tuple[float, float]],
    progress: float,
    noise_m: float = 50.0,
) -> Tuple[float, float]:
    """Return (lat, lon) at a given progress [0, 1] along the route.

    Adds Gaussian noise (~noise_m metres) to simulate GPS jitter.
    1 degree of latitude ~ 111 km.
    """
    progress = max(0.0, min(1.0, progress))

    if progress >= 1.0:
        lat, lon = route[-1]
    elif progress <= 0.0:
        lat, lon = route[0]
    else:
        seg_lengths = _segment_lengths(route)
        total = sum(seg_lengths)
        target_dist = progress * total

        cumulative = 0.0
        for i, seg_len in enumerate(seg_lengths):
            if cumulative + seg_len >= target_dist:
                # interpolate within this segment
                frac = (target_dist - cumulative) / seg_len if seg_len > 0 else 0.0
                lat = route[i][0] + frac * (route[i + 1][0] - route[i][0])
                lon = route[i][1] + frac * (route[i + 1][1] - route[i][1])
                break
            cumulative += seg_len
        else:
            lat, lon = route[-1]

    # Add Gaussian noise (~noise_m)
    noise_deg = noise_m / 111_000.0  # rough conversion metres -> degrees
    lat += random.gauss(0, noise_deg)
    lon += random.gauss(0, noise_deg)

    return lat, lon
