"""Teste de fumaça do fluxo de CT-e de custo (sap/custo.py).

Não valida a navegação de tela do SAP (isso só é possível com o SAP GUI real),
mas garante que o código Python percorre o fluxo inteiro sem erros de digitação,
atributo ou tipo — o mesmo papel que MagicMock cumpre aqui.
"""
import unittest
from unittest.mock import MagicMock

from pydosap.sap import custo
from pydosap.sap.session import SapSession


def sap_falso(**status_por_campo) -> SapSession:
    """SapSession com uma sessão SAP totalmente mockada; `status_por_campo` define
    valores fixos de retorno para campos de texto específicos (ex.: RM08M-DIFFERENZ)."""
    sap = SapSession()
    raw = MagicMock()
    raw.Busy = False
    raw.ActiveWindow.Text = ""
    raw.ActiveWindow.Name = "wnd[0]"
    raw.Info.Client = "100"

    def find_by_name_ex(nome, tipo):
        campo = MagicMock()
        campo.Text = status_por_campo.get(nome, "0,00")
        campo.RowCount = 0
        return campo

    raw.ActiveWindow.FindByNameEx.side_effect = find_by_name_ex
    raw.FindById.return_value.Text = status_por_campo.get("__sbar__", "Salvo")
    sap._ses = raw  # bypassa connect(): injeta a sessão "conectada" diretamente
    return sap


class SimularFaturaTests(unittest.TestCase):
    def test_sem_diferenca_sucesso(self):
        sap = sap_falso(G_TOT_SIMUL_NF="100,00", G_TOT_SIMUL_FAT="100,00")
        r = custo.simular_fatura(sap, "4" * 44)
        self.assertTrue(r.sucesso)

    def test_com_diferenca_falha(self):
        sap = sap_falso(G_TOT_SIMUL_NF="100,00", G_TOT_SIMUL_FAT="150,00")
        r = custo.simular_fatura(sap, "4" * 44)
        self.assertFalse(r.sucesso)
        self.assertAlmostEqual(r.saldo, 50.0)

    def test_nf_nao_encontrada(self):
        sap = sap_falso()
        sap._ses.ActiveWindow.Text = "Mensagens"
        r = custo.simular_fatura(sap, "4" * 44)
        self.assertFalse(r.sucesso)
        self.assertIn("Nenhuma nota", r.mensagem)


class LancarNotaTests(unittest.TestCase):
    def test_nota_ja_lancada(self):
        sap = sap_falso()
        sap._ses.FindById.return_value.GetCellValue.side_effect = lambda r, c: {
            0: "5000175939", 1: "5106412862"
        }[r]
        r = custo.lancar_nota(sap, "4" * 44)
        self.assertTrue(r.sucesso)
        self.assertEqual(r.migo, "5000175939")
        self.assertEqual(r.miro, "5106412862")
        self.assertIn("já estava lançada", r.mensagem)


class FornecerOrdemVendaTests(unittest.TestCase):
    def test_carga_para_estoque_nao_herda_mensagem_anterior(self):
        """Corrige um bug do VBA original: ao pular uma ordem "Carga para estoque",
        a mensagem/remessa não deve herdar o resultado da ordem processada antes dela."""
        sap = sap_falso()
        ordens = [
            {"pedido": "4501000001", "ordem": "210000001", "mensagem": ""},
            {"pedido": "4501000002", "ordem": "", "mensagem": "Carga para estoque"},
        ]
        sap._ses.FindById.return_value.Text = "Documento 210000099 foi gravado"
        resultado = custo.fornecer_ordem_venda(sap, ordens)

        self.assertEqual(resultado[0].remessa, "210000099")
        self.assertEqual(resultado[1].mensagem, "Carga para estoque")
        self.assertEqual(resultado[1].remessa, "")


class LancarMiroCustoTests(unittest.TestCase):
    def test_fluxo_feliz_extrai_numero_do_documento(self):
        sap = sap_falso(
            RM08M_DIFFERENZ="0,00",
            **{"RM08M-DIFFERENZ": "0,00", "__sbar__": "Não foi possível"},
        )
        sap._ses.FindById.return_value.Text = "Documento nº 5106412878 foi criado"

        cte = {
            "filial": {"empresa": "1000", "localneg": "2005"},
            "cteProt": {"infProt": {"chCTe": "4" * 34 + "12345678" + "1", "nProt": "123", "dhRecbto": "2026-09-18T10:00:00"}},
            "infCte": {
                "ide": {"dhEmi": "2026-09-18T00:00:00", "UFIni": "35", "cMunIni": "3550308",
                        "UFFim": "33", "cMunFim": "3304557"},
                "vPrest": {"vTPrest": "180.52"},
                "emit": {"CNPJ": "02633583001195"},
                "chaves": ["4" * 44],
            },
            "calculos": {"iva_calculado": "IB", "valor_liquido": 180.52},
            "integracao": {"status": "CONFIRMADO", "mensagem": ""},
            "importadora": "",
        }
        r = custo.lancar_miro_custo(sap, cte)
        self.assertTrue(r.sucesso)
        self.assertEqual(r.miro, "5106412878")


if __name__ == "__main__":
    unittest.main()


class ServicoCustoLogTests(unittest.TestCase):
    """Regra de ouro: todo lançamento de CT-e de custo precisa gerar log (a versão
    anterior do serviço não registrava nada)."""

    def _api(self, chaves=("4" * 44,)):
        api = MagicMock()
        api.buscar_cte_custo.return_value = {"infCte": {"chaves": list(chaves)}}
        return api

    def test_loga_mesmo_quando_a_simulacao_falha(self):
        from pydosap.services.custo import CteCustoService

        api = self._api()
        sap = sap_falso(G_TOT_SIMUL_NF="100,00", G_TOT_SIMUL_FAT="150,00")
        svc = CteCustoService(api, sap, usuario="fulano")

        resultado = svc.lancar("4" * 44)

        self.assertFalse(resultado.sucesso)
        api.inserir_log.assert_called_once()
        log = api.inserir_log.call_args[0][0]
        self.assertEqual(log["tipo_lancamento"], "CUSTO")
        self.assertEqual(log["mandante"], "100")
        self.assertEqual(log["excel_user"], "FULANO")
        self.assertFalse(log["sucesso"])
        self.assertIn("Diferença", log["mensagem"])

    def test_loga_mesmo_com_erro_inesperado_na_api(self):
        from pydosap.services.custo import CteCustoService

        api = MagicMock()
        api.buscar_cte_custo.side_effect = RuntimeError("timeout na API")
        sap = sap_falso()
        svc = CteCustoService(api, sap)

        resultado = svc.lancar("4" * 44)

        self.assertFalse(resultado.sucesso)
        self.assertIn("timeout na API", resultado.mensagem)
        api.inserir_log.assert_called_once()
        self.assertFalse(api.inserir_log.call_args[0][0]["sucesso"])


