import unittest

from pydosap.cte_columns import ORDEM, ordenar_colunas


class OrdenarColunasTests(unittest.TestCase):
    def test_segue_a_ordem_definida(self):
        presentes = ["chave", "lancado", "lancar", "centro", "regiao"]
        self.assertEqual(ordenar_colunas(presentes), ["lancado", "lancar", "regiao", "centro", "chave"])

    def test_desconhecidas_vao_para_o_final_na_ordem_original(self):
        presentes = ["lancar", "campoNovo", "regiao", "outroCampo"]
        self.assertEqual(ordenar_colunas(presentes), ["lancar", "regiao", "campoNovo", "outroCampo"])

    def test_pedido_e_resposta_ficam_no_meio_nao_no_final(self):
        presentes = list(ORDEM)  # todas as colunas conhecidas presentes
        resultado = ordenar_colunas(presentes)
        self.assertLess(resultado.index("pedido"), resultado.index("categoria"))
        self.assertLess(resultado.index("resposta"), resultado.index("categoria"))
        self.assertNotEqual(resultado[-1], "resposta")

    def test_remove_duplicatas_preservando_primeira_posicao(self):
        presentes = ["lancar", "lancar", "regiao"]
        self.assertEqual(ordenar_colunas(presentes), ["lancar", "regiao"])


if __name__ == "__main__":
    unittest.main()
