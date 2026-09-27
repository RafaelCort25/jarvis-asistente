"""Frases motivacionales curadas.

Frases clasicas de autores conocidos, sin duplicados y con encoding correcto.
"""
import random
from skills.base import Skill


# Frases curadas (unicas, con autor)
FRASES = [
    # Steve Jobs
    {"texto": "La unica forma de hacer un gran trabajo es amar lo que haces.", "autor": "Steve Jobs"},
    {"texto": "Tu tiempo es limitado, no lo desperdicies viviendo la vida de otra persona.", "autor": "Steve Jobs"},
    {"texto": "La innovacion distingue a un lider de un seguidor.", "autor": "Steve Jobs"},

    # Albert Einstein
    {"texto": "La imaginacion es mas importante que el conocimiento.", "autor": "Albert Einstein"},
    {"texto": "No tienes que saberlo todo, solo tienes que ser curioso.", "autor": "Albert Einstein"},
    {"texto": "La vida es como andar en bicicleta. Para mantener el equilibrio, debes seguir moviendote.", "autor": "Albert Einstein"},

    # Nelson Mandela
    {"texto": "La educacion es el arma mas poderosa que puedes usar para cambiar el mundo.", "autor": "Nelson Mandela"},
    {"texto": "Siempre parece imposible hasta que se hace.", "autor": "Nelson Mandela"},
    {"texto": "El valor no es la ausencia de miedo, sino el triunfo sobre el.", "autor": "Nelson Mandela"},

    # Mahatma Gandhi
    {"texto": "Se el cambio que quieres ver en el mundo.", "autor": "Mahatma Gandhi"},
    {"texto": "La fuerza no proviene de la capacidad fisica, sino de una voluntad indomable.", "autor": "Mahatma Gandhi"},
    {"texto": "Un ojo por un ojo solo hara que todo el mundo quede ciego.", "autor": "Mahatma Gandhi"},

    # Confucio
    {"texto": "Elige un trabajo que te guste y no tendras que trabajar ni un dia de tu vida.", "autor": "Confucio"},
    {"texto": "Nuestra mayor gloria no esta en no caer nunca, sino en levantarnos cada vez que caemos.", "autor": "Confucio"},
    {"texto": "Lo que no quieras para ti, no lo hagas a los demas.", "autor": "Confucio"},

    # Aristoteles
    {"texto": "Somos lo que hacemos repetidamente. La excelencia, entonces, no es un acto sino un habito.", "autor": "Aristoteles"},
    {"texto": "La paciencia es amarga, pero sus frutos son dulces.", "autor": "Aristoteles"},

    # Mark Twain
    {"texto": "Dentro de veinte anos estaras mas decepcionado por las cosas que no hiciste que por las que hiciste.", "autor": "Mark Twain"},
    {"texto": "El secreto para salir adelante es comenzar.", "autor": "Mark Twain"},
    {"texto": "Nunca dejes que la escuela interfiera con tu educacion.", "autor": "Mark Twain"},

    # Otros clasicos
    {"texto": "El unico modo de hacer un gran trabajo es amar lo que haces.", "autor": "Steve Jobs"},
    {"texto": "La mejor manera de predecir el futuro es inventarlo.", "autor": "Alan Kay"},
    {"texto": "No cuentes los dias, haz que los dias cuenten.", "autor": "Muhammad Ali"},
    {"texto": "La disciplina es el puente entre las metas y los logros.", "autor": "Jim Rohn"},
    {"texto": "Si quieres ir rapido, ve solo. Si quieres llegar lejos, ve acompanado.", "autor": "Proverbio africano"},
    {"texto": "El pesimista ve dificultad en cada oportunidad. El optimista ve oportunidad en cada dificultad.", "autor": "Winston Churchill"},
    {"texto": "El exito es la suma de pequenos esfuerzos repetidos dia tras dia.", "autor": "Robert Collier"},
    {"texto": "No es que tengamos poco tiempo, es que perdemos mucho.", "autor": "Seneca"},
    {"texto": "El que mueve montanas empieza apartando piedras pequenas.", "autor": "Confucio"},
    {"texto": "Haz de tu vida un sueno y de tu sueno una realidad.", "autor": "Paulo Coelho"},
    {"texto": "La creatividad es la inteligencia divirtiendose.", "autor": "Albert Einstein"},
    {"texto": "El mejor momento para plantar un arbol fue hace veinte anos. El segundo mejor momento es ahora.", "autor": "Proverbio chino"},
]


class FrasesSkill(Skill):
    name = "frases"
    description = "Frases motivacionales clasicas con autor"

    def run(self, action, params):
        if action == "random":
            return self._random()
        if action == "by_author":
            return self._by_author(params.get("autor", ""))
        if action == "list":
            return self._list()
        if action == "count":
            return self._count()
        return {
            "thought": f"Accion desconocida: {action}",
            "display": f"Accion desconocida: {action}",
            "voice": "No entendi esa accion.",
        }

    def _random(self):
        frase = random.choice(FRASES)
        texto = f"{frase['texto']} - {frase['autor']}"
        return {
            "thought": f"Elegir frase aleatoria de {frase['autor']}",
            "display": f'"{frase["texto"]}"\n\n- **{frase["autor"]}**',
            "voice": f'{frase["texto"]} Dijo {frase["autor"]}.',
        }

    def _by_author(self, autor):
        if not autor:
            return {
                "thought": "Falta autor",
                "display": "Dime el autor. Ej: 'frase de Einstein'",
                "voice": "Dime el autor.",
            }
        autor_low = autor.lower().strip()
        encontradas = [f for f in FRASES if autor_low in f["autor"].lower()]
        if not encontradas:
            return {
                "thought": f"Sin frases de {autor}",
                "display": f"No tengo frases de **{autor}**.",
                "voice": f"No tengo frases de {autor}.",
            }
        frase = random.choice(encontradas)
        return {
            "thought": f"Frase de {frase['autor']}",
            "display": f'"{frase["texto"]}"\n\n- **{frase["autor"]}**',
            "voice": f'{frase["texto"]} Dijo {frase["autor"]}.',
        }

    def _list(self):
        lineas = [f"Tengo {len(FRASES)} frases motivacionales:"]
        for i, f in enumerate(FRASES, 1):
            lineas.append(f'  {i}. "{f["texto"][:60]}..." - {f["autor"]}')
        return {
            "thought": f"Listar {len(FRASES)} frases",
            "display": "\n".join(lineas),
            "voice": f"Tengo {len(FRASES)} frases motivacionales guardadas.",
        }

    def _count(self):
        return {
            "thought": "Contar frases",
            "display": f"Tengo **{len(FRASES)}** frases motivacionales.",
            "voice": f"Tengo {len(FRASES)} frases.",
        }