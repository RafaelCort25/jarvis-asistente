class Skill:
    name = "base"
    description = "Skill base"

    def run(self, action, params):
        """Ejecuta una accion con parametros. Debe sobrescribirse."""
        raise NotImplementedError