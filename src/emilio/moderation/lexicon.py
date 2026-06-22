"""Lessico italiano per il sistema di supervisione di Emilio.

Qui vivono gli elenchi di termini. Sono separati dal motore (engine.py) così
puoi ampliarli senza toccare la logica.

Tre blocchi:
  * PROFANITY        -> parolacce / volgarità (match diretto, con tolleranza)
  * BLASPHEMY_DIVINE -> entità "divine" usate nelle bestemmie
  * BLASPHEMY_QUALIFIER -> qualificatori offensivi che, accostati a un'entità
                          divina, formano una bestemmia (es. "dio" + "cane")
  * BLASPHEMY_FIXED  -> bestemmie/espressioni fisse non coperte dalla
                        combinazione entità+qualificatore

Note sulla severità (severity):
  5 = bestemmia                3 = volgarità forte
  2 = volgarità media          1 = volgarità lieve

Il campo `inflect` indica se permettere desinenze italiane finali
(a/e/i/o, -ata, -one, -oso ...). Si usa per gli "stem" (radici), es. "cazz"
intercetta cazzo, cazzi, cazzata, cazzone.
"""

# (radice/parola, severità, inflect)
PROFANITY: list[tuple[str, int, bool]] = [
    # --- volgarità forti ---
    ("cazz", 3, True),          # cazzo, cazzi, cazzata, cazzone...
    ("vaffancul", 3, True),     # vaffanculo
    ("vaffanbagn", 2, True),    # vaffanbagno (eufemismo)
    ("minchi", 3, True),        # minchia, minchione
    ("incul", 3, True),         # inculare, inculata
    ("troia", 3, False),
    ("troie", 3, False),
    ("puttan", 3, True),        # puttana, puttanata
    ("mignott", 3, True),
    ("figa", 3, False),
    ("fighe", 3, False),
    ("fica", 3, False),
    ("fiche", 3, False),
    ("sborr", 3, True),
    ("pompin", 3, True),
    ("bocchin", 3, True),
    ("ricchion", 3, True),
    ("froci", 3, True),         # slur
    # --- volgarità medie ---
    ("stronz", 2, True),
    ("merd", 2, True),
    ("coglion", 2, True),
    ("mona", 2, False),         # veneto: "va' in mona" (figa / scemo)
    ("mone", 2, False),
    ("zoccol", 2, True),
    ("bastard", 2, True),
    ("fott", 2, True),          # fottuto, fottere
    ("incazz", 2, True),
    ("rincoglion", 2, True),
    ("segaiol", 2, True),
    # --- volgarità lievi ---
    ("scazz", 1, True),
    ("sfigat", 1, True),
    ("pirla", 1, False),
    ("culo", 1, False),
    ("culi", 1, False),
    ("scoreggi", 1, True),
]

# Entità "divine" (da sole NON vengono censurate: servono parlare di religione)
BLASPHEMY_DIVINE: list[str] = [
    "dio", "dii", "iddio",
    "madonna", "madonne",
    "madona", "madone",         # grafia veneta (una sola n)
    "cristo", "cristi",
    "gesu", "gesù", "gesucristo",
    "ostia", "ostie",
    "sacramento",
    "eucaristia",
    "vergine",
    "padreterno",
]

# Qualificatori offensivi: divina + qualificatore (in qualunque ordine) = bestemmia
BLASPHEMY_QUALIFIER: list[str] = [
    "cane", "can",
    "porco", "porca",
    "maiale", "maiala",
    "boia",
    "ladro", "ladra",
    "bastardo", "bastarda",
    "merda", "merdoso",
    "stronzo",
    "infame",
    "schifoso", "schifosa",
    "bestia",
    "troia",
    "puttana",
    "zoccola",
    "sporco", "sporca",
    "lurido", "lurida",
    "bono", "bona",          # "dio bono" (eufemismo)
    "cantante",              # "dio cantante" (eufemismo)
    "impestato", "impestata",
]

# Bestemmie/espressioni fisse (anche multi-parola) non generate dalla combinazione
BLASPHEMY_FIXED: list[str] = [
    "dio morto",
    "cristo morto",
    "madonna morta",
    "dio stramaledetto",
    "ostia santa",
    "porco il signore",
    "madonna del",          # incipit volgare comune ("madonna del ...")
]

# Insulti/contraddizioni che "provocano" Emilio (oltre alle parolacce vere):
# servono a farlo infuriare anche quando l'offesa non è turpiloquio.
PROVOCAZIONI: list[str] = [
    "scem", "cretin", "idiot", "imbecill", "deficien", "stupid", "fesso",
    "tonto", "rincoglion", "fallito", "inutile", "buono a nulla", "non vali",
    "fai schifo", "fai pena", "ti odio", "sei brutto", "sei vecchio",
    "rottame", "ferraglia", "catorcio", "scatoletta", "bidone di bulloni",
    "ti sbagli", "hai torto", "non è vero", "non e vero", "non sono d'accordo",
    "ma stai zitto", "stai zitto", "taci",
]

# Interiezioni innocue con cui sostituire una bestemmia censurata
INTERJECTIONS: list[str] = [
    "santo cielo",
    "perbacco",
    "accidenti",
    "caspiterina",
    "porca paletta",
    "mannaggia",
]
