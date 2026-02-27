# %% Pakete
import re
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from langchain_groq import ChatGroq
from dotenv import load_dotenv

import dash
from dash import dcc, html, Input, Output, State, callback
import dash_bootstrap_components as dbc


# ── Supermarkt-Abteilungen in typischer Laufreihenfolge ──────────────────────
SUPERMARKT_REIHENFOLGE = [
    "Obst & Gemüse",
    "Backwaren",
    "Milchprodukte & Eier",
    "Fleisch & Wurst",
    "Fisch & Meeresfrüchte",
    "Tiefkühlkost",
    "Konserven & Fertiggerichte",
    "Nudeln, Reis & Getreide",
    "Gewürze, Öle & Essig",
    "Backen & Süßes",
    "Getränke",
    "Sonstiges",
]

ABTEILUNG_ICONS = {
    "Obst & Gemüse": "🥬",
    "Backwaren": "🍞",
    "Milchprodukte & Eier": "🥚",
    "Fleisch & Wurst": "🥩",
    "Fisch & Meeresfrüchte": "🐟",
    "Tiefkühlkost": "🧊",
    "Konserven & Fertiggerichte": "🥫",
    "Nudeln, Reis & Getreide": "🍝",
    "Gewürze, Öle & Essig": "🧂",
    "Backen & Süßes": "🍰",
    "Getränke": "🥤",
    "Sonstiges": "🛒",
}

# ── Pydantic-Modelle (erweitertes Schema) ─────────────────────────────────────
class Zutat(BaseModel):
    name: str = Field(description="Name der Zutat")
    menge: str = Field(description="Benötigte Menge, z.B. '200 g', '2 Stück', '1 EL'")
    abteilung: str = Field(
        description=(
            "Supermarkt-Abteilung. Muss exakt eine dieser Optionen sein: "
            + ", ".join(SUPERMARKT_REIHENFOLGE)
        )
    )
    preis_eur: float = Field(
        description="Geschätzter aktueller Einzelhandelspreis in Euro (Deutschland 2025) für die angegebene Menge"
    )


class RezeptAusgabe(BaseModel):
    titel: str = Field(description="Vollständiger Rezepttitel")
    kurzbeschreibung: str = Field(description="Appetitliche Kurzbeschreibung des Gerichts (2–3 Sätze)")
    zutaten: list[Zutat] = Field(description="Alle benötigten Zutaten mit Supermarkt-Abteilung und Preisen")
    zubereitung: str = Field(description="Detaillierte Zubereitungsschritte, jeder Schritt auf einer neuen Zeile")
    vorbereitungszeit: int = Field(description="Vorbereitungszeit in Minuten")
    kochzeit: int = Field(description="Koch-/Backzeit in Minuten")
    gesamtzeit: int = Field(description="Gesamtzeit in Minuten")
    portionen: int = Field(description="Anzahl der Portionen / Personen")
    schwierigkeit: str = Field(description="Schwierigkeitsgrad: Einfach, Mittel oder Schwer")


# ── LangChain-Chain ───────────────────────────────────────────────────────────
parser = PydanticOutputParser(pydantic_object=RezeptAusgabe)

SYSTEM_PROMPT = """\
Du bist ein erfahrener Koch und Einkaufsexperte für den deutschen Markt.
Der Nutzer nennt dir ein Gericht. Du erstellst:
- Ein vollständiges Rezept mit allen Zutaten
- Aktuelle deutsche Supermarktpreise (REWE / EDEKA / Aldi, Stand 2025) für die jeweils benötigte Menge
- Jede Zutat wird einer Supermarkt-Abteilung zugeordnet
- Nummerierte Zubereitungsschritte (z.B. "1. Wasser aufkochen …")

{schema}"""

prompt_template = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("user", "Erstelle ein detailliertes Rezept für: {gericht}"),
]).partial(schema=parser.get_format_instructions())

model = ChatGroq(model="openai/gpt-oss-120b")
chain = prompt_template | model | parser


# ── Hilfsfunktionen für die UI ────────────────────────────────────────────────
def erstelle_einkaufsliste(zutaten: list[Zutat]) -> dbc.Table:
    """Baut eine nach Supermarkt-Abteilungen sortierte Einkaufsliste als Tabelle."""
    # Nach Abteilung gruppieren
    gruppen: dict[str, list[Zutat]] = {}
    for z in zutaten:
        gruppen.setdefault(z.abteilung, []).append(z)

    # Sortierung nach typischer Supermarkt-Reihenfolge
    sortierte_gruppen = sorted(
        gruppen.items(),
        key=lambda x: (
            SUPERMARKT_REIHENFOLGE.index(x[0])
            if x[0] in SUPERMARKT_REIHENFOLGE
            else 99
        ),
    )

    zeilen = []
    gesamt = 0.0

    for abteilung, artikel in sortierte_gruppen:
        icon = ABTEILUNG_ICONS.get(abteilung, "🛒")
        # Abteilungs-Header
        zeilen.append(
            html.Tr(
                html.Td(
                    [html.Span(icon, className="me-2"), html.Strong(abteilung)],
                    colSpan=3,
                    style={
                        "backgroundColor": "#e8f5e9",
                        "padding": "6px 12px",
                        "fontSize": "0.9rem",
                        "letterSpacing": "0.03em",
                    },
                )
            )
        )
        for z in artikel:
            gesamt += z.preis_eur
            zeilen.append(
                html.Tr([
                    html.Td(z.name, style={"paddingLeft": "2rem"}),
                    html.Td(z.menge, className="text-muted small"),
                    html.Td(
                        f"{z.preis_eur:.2f} €",
                        className="text-end fw-semibold",
                        style={"whiteSpace": "nowrap"},
                    ),
                ])
            )

    # Gesamtzeile
    zeilen.append(
        html.Tr(
            [
                html.Td(html.Strong("Gesamt ca."), colSpan=2),
                html.Td(
                    html.Strong(f"{gesamt:.2f} €"),
                    className="text-end text-success fs-6",
                ),
            ],
            style={"borderTop": "2px solid #4caf50"},
        )
    )

    return dbc.Table(
        [
            html.Thead(
                html.Tr([
                    html.Th("Zutat", style={"width": "50%"}),
                    html.Th("Menge", style={"width": "25%"}),
                    html.Th("Preis", className="text-end", style={"width": "25%"}),
                ])
            ),
            html.Tbody(zeilen),
        ],
        bordered=True,
        hover=True,
        responsive=True,
        className="align-middle mb-0",
        size="sm",
    )


def erstelle_zubereitung(zubereitung: str) -> html.Ol:
    """Formatiert nummerierte Zubereitungsschritte als geordnete Liste."""
    schritte = [s.strip() for s in zubereitung.splitlines() if s.strip()]
    items = []
    for schritt in schritte:
        bereinigt = re.sub(r"^\d+[\.\)]\s*", "", schritt)
        items.append(html.Li(bereinigt, className="mb-2"))
    return html.Ol(items, className="ps-3 mb-0")


def erstelle_ergebnis(rezept: RezeptAusgabe) -> html.Div:
    """Baut die vollständige Ergebnisansicht."""
    schwierigkeit_farbe = {
        "Einfach": "success",
        "Mittel": "warning",
        "Schwer": "danger",
    }.get(rezept.schwierigkeit, "secondary")

    return html.Div([
        # ── Rezept-Header ──────────────────────────────────────────────────
        dbc.Card(
            dbc.CardBody(
                dbc.Row([
                    dbc.Col([
                        html.H2(rezept.titel, className="fw-bold mb-1"),
                        html.P(rezept.kurzbeschreibung, className="text-muted mb-2"),
                        dbc.Stack(
                            [
                                dbc.Badge(
                                    f"👥 {rezept.portionen} Portionen",
                                    color="light",
                                    text_color="dark",
                                    className="border",
                                ),
                                dbc.Badge(rezept.schwierigkeit, color=schwierigkeit_farbe),
                            ],
                            direction="horizontal",
                            gap=2,
                        ),
                    ], md=8),
                    dbc.Col(
                        dbc.Card(
                            dbc.CardBody([
                                _zeitblock("⏱️", "Vorbereitung", rezept.vorbereitungszeit),
                                _zeitblock("🔥", "Kochen", rezept.kochzeit),
                                _zeitblock("⌛", "Gesamt", rezept.gesamtzeit, bold=True),
                            ]),
                            className="bg-light border-0 h-100",
                        ),
                        md=4,
                    ),
                ], align="center"),
            ),
            className="shadow-sm mb-4",
        ),

        # ── Einkaufsliste + Zubereitung ────────────────────────────────────
        dbc.Row([
            dbc.Col([
                html.H5(
                    ["🛒 ", html.Span("Einkaufsliste", className="ms-1")],
                    className="mb-3 text-success fw-bold",
                ),
                erstelle_einkaufsliste(rezept.zutaten),
            ], md=6, className="mb-4"),

            dbc.Col([
                html.H5(
                    ["📋 ", html.Span("Zubereitung", className="ms-1")],
                    className="mb-3 text-primary fw-bold",
                ),
                dbc.Card(
                    dbc.CardBody(erstelle_zubereitung(rezept.zubereitung)),
                    className="shadow-sm",
                ),
            ], md=6, className="mb-4"),
        ]),
    ])


def _zeitblock(icon: str, label: str, minuten: int, bold: bool = False) -> html.Div:
    text = f"{minuten} Min."
    return html.Div(
        [
            html.Span(f"{icon} ", style={"fontSize": "1rem"}),
            html.Span(label + ": ", className="text-muted small"),
            html.Strong(text) if bold else html.Span(text),
        ],
        className="mb-1",
    )


# ── Dash App ──────────────────────────────────────────────────────────────────
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
    ],
    title="Rezept & Einkaufsplaner",
)

app.layout = dbc.Container(
    [
        # ── Navbar ────────────────────────────────────────────────────────
        dbc.Navbar(
            dbc.Container(
                dbc.NavbarBrand(
                    "🛒 Rezept & Einkaufsplaner",
                    style={"fontSize": "1.4rem", "fontWeight": "bold"},
                )
            ),
            color="success",
            dark=True,
            className="mb-4 rounded",
        ),

        # ── Eingabe ───────────────────────────────────────────────────────
        dbc.Card(
            dbc.CardBody([
                html.H5("Welches Gericht möchten Sie kochen?", className="mb-3"),
                dbc.Row([
                    dbc.Col(
                        dcc.Input(
                            id="gericht-input",
                            placeholder="z.B. Spaghetti Carbonara, Wiener Schnitzel, Tiramisu …",
                            type="text",
                            debounce=False,
                            n_submit=0,
                            className="form-control form-control-lg",
                            style={"borderRadius": "0.5rem"},
                        ),
                        md=9,
                        className="mb-2 mb-md-0",
                    ),
                    dbc.Col(
                        dbc.Button(
                            [html.I(className="bi bi-search me-2"), "Rezept erstellen"],
                            id="submit-btn",
                            color="success",
                            size="lg",
                            className="w-100",
                            n_clicks=0,
                        ),
                        md=3,
                    ),
                ], align="center"),
                html.Small(
                    "Tipp: Drücken Sie Enter oder klicken Sie auf den Button. "
                    "Die Einkaufsliste wird nach typischer Supermarkt-Reihenfolge sortiert.",
                    className="text-muted mt-2 d-block",
                ),
            ]),
            className="shadow-sm mb-4",
        ),

        # ── Ergebnis mit Ladeanzeige ───────────────────────────────────────
        dcc.Loading(
            html.Div(id="ergebnis-container"),
            type="circle",
            color="#198754",
        ),
    ],
    fluid=True,
    className="px-3 px-md-5 pb-5",
)


# ── Callback ──────────────────────────────────────────────────────────────────
@callback(
    Output("ergebnis-container", "children"),
    Input("submit-btn", "n_clicks"),
    Input("gericht-input", "n_submit"),
    State("gericht-input", "value"),
    prevent_initial_call=True,
)
def rezept_erstellen(n_clicks, n_submit, gericht):
    if not gericht or not gericht.strip():
        return dbc.Alert("Bitte geben Sie zunächst ein Gericht ein.", color="warning", className="mt-2")

    try:
        rezept: RezeptAusgabe = chain.invoke({"gericht": gericht.strip()})
        return erstelle_ergebnis(rezept)
    except Exception as exc:
        return dbc.Alert(
            [html.Strong("Fehler beim Abrufen des Rezepts: "), str(exc)],
            color="danger",
            className="mt-2",
        )


# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=8050)
