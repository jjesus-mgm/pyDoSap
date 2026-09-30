import unittest

from pydosap.formatting import converter_como_original as _converter_como_original


class ConversaoTests(unittest.TestCase):
    def test_mantem_tipo_inteiro(self):
        self.assertEqual(_converter_como_original("42", 1), 42)
        self.assertIsInstance(_converter_como_original("42", 1), int)

    def test_mantem_tipo_float_aceita_virgula(self):
        self.assertEqual(_converter_como_original("12,5", 1.0), 12.5)

    def test_texto_invalido_mantem_texto(self):
        self.assertEqual(_converter_como_original("abc", 1), "abc")

    def test_booleano_a_partir_de_texto(self):
        self.assertTrue(_converter_como_original("Sim", True))
        self.assertFalse(_converter_como_original("Não", True))

    def test_string_permanece_string(self):
        self.assertEqual(_converter_como_original(" MAT2 ", "MAT1"), "MAT2")


if __name__ == "__main__":
    unittest.main()
