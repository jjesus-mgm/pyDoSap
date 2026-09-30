import unittest

from pydosap.models import ControleLancamento
from pydosap.sap.fatura import lancar_fatura
from pydosap.sap.pedido import criar_pedido_frete
from pydosap.services.lancamento import LancamentoService

from .fakes import CFG, FakeApi, FakeSap, novo_cte

MSG_PEDIDO = "Ped.padrão criado sob o número 4500123456"
MSG_MIRO = "Documento 5105123456 foi registrado"


def cte_pronto(**extra):
    cte = novo_cte(codFornecedor="100200", **extra)
    cte["cfgLancamento"] = dict(CFG)
    return cte


class PedidoTests(unittest.TestCase):
    def test_sucesso_extrai_numero(self):
        sap = FakeSap(ao_teclar={11: ("S", MSG_PEDIDO)})
        r = criar_pedido_frete(sap, cte_pronto())
        self.assertTrue(r.sucesso)
        self.assertEqual(r.valor, "4500123456")
        self.assertEqual(sap.transacoes(), ["me21n"])
        self.assertEqual(sap.campos["MEPO1211-NETPR"], 12345678)
        self.assertEqual(sap.tabelas["SAPLEKPATC_0111"].linhas[0][2], "100200")

    def test_sem_numero_na_mensagem_falha(self):
        sap = FakeSap(ao_teclar={11: ("S", "Salvo")})
        r = criar_pedido_frete(sap, cte_pronto())
        self.assertFalse(r.sucesso)
        self.assertEqual(r.valor, "")

    def test_erro_de_material(self):
        sap = FakeSap()
        original = sap.send_enter

        def enter():
            original()
            if sap.campos.get("MEPO1211-EMATN"):
                sap.status = ("E", "Material MAT1 não existe")
        sap.send_enter = enter
        r = criar_pedido_frete(sap, cte_pronto())
        self.assertFalse(r.sucesso)
        self.assertIn("Material", r.mensagem)
        self.assertNotIn(("vkey", 11), sap.chamadas)  # não chegou a salvar

    def test_pedagio_preenche_segunda_linha(self):
        cte = cte_pronto(possuiPedagio=True)
        cte["calculos"].update(considerarPedagio=True, valorPedidoPedagio=99000)
        sap = FakeSap(ao_teclar={11: ("S", MSG_PEDIDO)})
        criar_pedido_frete(sap, cte)
        itens = sap.tabelas["SAPLMEGUITC_1211"].linhas[1]
        self.assertEqual(itens[4], "PED1")
        self.assertEqual(itens[10], 99000)


class FaturaTests(unittest.TestCase):
    def sap(self, diferenca):
        return FakeSap(ao_teclar={11: ("S", MSG_MIRO)}, textos={"RM08M-DIFFERENZ": diferenca})

    def test_sucesso(self):
        sap = self.sap(["0,00"])
        cte = cte_pronto(pedido="4500123456", chamado="CH-1")
        r = lancar_fatura(sap, cte)
        self.assertTrue(r.sucesso)
        self.assertEqual(r.valor, "5105123456")
        self.assertEqual(sap.transacoes(), ["miro"])
        self.assertEqual(sap.campos["INVFO-WRBTR"], "1500,50")
        self.assertEqual(sap.campos["INVFO-BLDAT"], "01.09.2026")
        self.assertEqual(sap.campos["INVFO-BKTXT"], "CH-1")
        self.assertNotIn("INVFO-BUDAT", sap.campos)

    def test_data_de_lancamento_informada(self):
        sap = self.sap(["0,00"])
        lancar_fatura(sap, cte_pronto(pedido="4500123456", dataLancamento="2026-09-18"))
        self.assertEqual(sap.campos["INVFO-BUDAT"], "18.09.2026")

    def test_saldo_troca_fm_e_refaz_uma_vez(self):
        sap = self.sap(["10,00-", "0,00"])
        cte = cte_pronto(pedido="4500123456")
        r = lancar_fatura(sap, cte)
        self.assertTrue(r.sucesso)
        self.assertEqual(sap.transacoes(), ["miro", "me21n", "miro"])
        self.assertTrue(cte["fornecedorPedidoModificado"])

    def test_saldo_persistente_nao_entra_em_loop(self):
        sap = self.sap(["10,00", "10,00"])
        r = lancar_fatura(sap, cte_pronto(pedido="4500123456"))
        # a segunda passada segue adiante mesmo com saldo (como no VBA): sem loop infinito
        self.assertEqual(sap.transacoes(), ["miro", "me21n", "miro"])
        self.assertTrue(r.sucesso)


class ServicoTests(unittest.TestCase):
    def rodar(self, api, sap, linhas, controle=None, stop=None):
        eventos = {"result": [], "status": [], "log": []}
        svc = LancamentoService(
            api, sap, usuario="fulano",
            on_result=lambda i, p, r, ok: eventos["result"].append((i, p, r, ok)),
            on_status=lambda i, s: eventos["status"].append((i, s)),
            on_log=eventos["log"].append,
            should_stop=stop,
        )
        resumo = svc.lancar(linhas, controle or ControleLancamento(chamado="CH-9"))
        return resumo, eventos

    def base(self, **extra):
        d = {"oidDocumento": "oid1", "chave": "35" + "1" * 42, "codFornecedor": 100200,
             "categoria": "FRETE", "pedido": "", "lancar": True}
        d.update(extra)
        return d

    def sap_ok(self):
        return FakeSap(ao_teclar={11: ("S", MSG_PEDIDO)}, textos={"RM08M-DIFFERENZ": ["0,00"]})

    def test_fluxo_completo(self):
        sap = self.sap_ok()
        # o mesmo status de sucesso serve ao pedido e à MIRO: o número extraído é o da mensagem
        sap.ao_teclar[11] = ("S", "Documento 5105123456 registrado. Pedido 4500123456")
        api = FakeApi()
        resumo, ev = self.rodar(api, sap, [(3, self.base())])
        self.assertEqual((resumo.total, resumo.sucesso, resumo.falha), (1, 1, 0))
        self.assertEqual(ev["result"][0][0], 3)
        self.assertTrue(ev["result"][0][3])
        self.assertEqual(ev["status"], [(3, "processando"), (3, "ok")])
        self.assertEqual(sap.transacoes(), ["me21n", "miro"])
        log = api.logs[0]
        self.assertEqual(set(log), {"chave", "data_hora", "sap_user", "excel_user", "sucesso",
                                    "mensagem", "dados_processados", "tipo_lancamento", "mandante"})
        self.assertTrue(log["chave"].startswith("chv35"))
        self.assertEqual(log["excel_user"], "FULANO")
        self.assertEqual(log["sap_user"], "SAPUSER")
        self.assertTrue(log["sucesso"])
        self.assertEqual(log["dados_processados"]["chamado"], "CH-9")
        self.assertEqual(log["tipo_lancamento"], "DESPESA")
        self.assertEqual(log["mandante"], "100")

    def test_pendencia_de_integracao_nao_toca_no_sap(self):
        sap = self.sap_ok()
        api = FakeApi(cte=novo_cte(possuiPendencia=True, mensagemIntegracao="CT-e sem integração"))
        resumo, ev = self.rodar(api, sap, [(0, self.base())])
        self.assertEqual(resumo.falha, 1)
        self.assertEqual(sap.chamadas, [])
        self.assertEqual(ev["result"][0][2], "CT-e sem integração")
        self.assertEqual(api.logs[0]["mensagem"], "CT-e sem integração")  # log com mensagem (no VBA ficava vazio)
        self.assertFalse(api.logs[0]["sucesso"])

    def test_ignorar_validacao(self):
        sap = self.sap_ok()
        api = FakeApi(cte=novo_cte(possuiPendencia=True, mensagemIntegracao="x"))
        self.rodar(api, sap, [(0, self.base())], ControleLancamento(ignorar_validacao=True))
        self.assertEqual(sap.transacoes()[0], "me21n")

    def test_pedido_existente_pula_criacao(self):
        sap = self.sap_ok()
        resumo, ev = self.rodar(FakeApi(), sap, [(0, self.base(pedido="4500999999"))])
        self.assertEqual(sap.transacoes(), ["miro"])
        self.assertEqual(ev["result"][0][1], "4500999999")

    def test_categoria_sem_configuracao(self):
        sap = self.sap_ok()
        resumo, ev = self.rodar(FakeApi(), sap, [(0, self.base(categoria="OUTRA"))])
        self.assertEqual(resumo.falha, 1)
        self.assertIn("OUTRA", ev["result"][0][2])
        self.assertEqual(sap.chamadas, [])

    def test_fornecedor_obrigatorio(self):
        sap = self.sap_ok()
        _, ev = self.rodar(FakeApi(), sap, [(0, self.base(codFornecedor=""))])
        self.assertIn("fornecedor", ev["result"][0][2].lower())
        self.assertEqual(sap.chamadas, [])

    def test_erro_em_um_cte_nao_derruba_o_lote(self):
        sap = self.sap_ok()
        api = FakeApi(falha_cte={"oid1": "timeout na API"})
        linhas = [(0, self.base(oidDocumento="oid1", chave="A" * 44)), (1, self.base(oidDocumento="oid2"))]
        resumo, ev = self.rodar(api, sap, linhas)
        self.assertEqual((resumo.sucesso, resumo.falha), (1, 1))
        self.assertIn("timeout na API", ev["result"][0][2])
        self.assertEqual(len(api.logs), 2)
        self.assertTrue(api.logs[0]["chave"].startswith("chvAAAA"))  # usa a chave da linha quando o CT-e não veio

    def test_parar_interrompe_o_lote(self):
        sap = self.sap_ok()
        parar = iter([False, True])
        resumo, _ = self.rodar(FakeApi(), sap, [(0, self.base()), (1, self.base(oidDocumento="oid2"))],
                               stop=lambda: next(parar))
        self.assertTrue(resumo.interrompido)
        self.assertEqual(resumo.sucesso + resumo.falha, 1)


if __name__ == "__main__":
    unittest.main()
