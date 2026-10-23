"""Upload de XML: leitura do retorno do Lincros e integração forçada (API falsa, sem rede)."""
import json
import tempfile
import unittest
from pathlib import Path

from pydosap.api_client import ApiError
from pydosap.services.upload import enviar_xmls, interpretar_integracao, interpretar_upload


def _upload(lincros: dict) -> str:
    return json.dumps({"status": "sucesso", "arquivo": "a.xml", "resposta_lincros": lincros})


class ApiFalsa:
    def __init__(self, upload=None, forcar=None):
        self._upload, self._forcar = upload, forcar
        self.chamadas: list[tuple] = []

    def upload_xml(self, nome, xml):
        self.chamadas.append(("upload", nome))
        r = self._upload(nome) if callable(self._upload) else self._upload
        if isinstance(r, Exception):
            raise r
        return r

    def forcar_integracao(self, nome, xml):
        self.chamadas.append(("forcar", nome))
        r = self._forcar(nome) if callable(self._forcar) else self._forcar
        if isinstance(r, Exception):
            raise r
        return r


class InterpretarUploadTest(unittest.TestCase):
    def test_com_oid_e_integrado(self):
        ok, msg = interpretar_upload(_upload({"oidCte": "87176222", "protocolo": 1, "status": "CONFIRMADO"}))
        self.assertTrue(ok)
        self.assertIn("87176222", msg)

    def test_confirmado_sem_oid_nao_e_integrado(self):
        ok, msg = interpretar_upload(_upload({"protocolo": 218534070, "status": "CONFIRMADO"}))
        self.assertFalse(ok)
        self.assertIn("NÃO foi integrado", msg)

    def test_resposta_fora_do_formato_mantem_ok(self):
        self.assertEqual(interpretar_upload("ok  "), (True, "ok"))


class InterpretarIntegracaoTest(unittest.TestCase):
    def test_integrado_para_lancar(self):
        ok, msg = interpretar_integracao({
            "status": "INTEGRADO", "oidDocumento": 9, "naView": True, "centro": "1004",
            "tipo": "DESPESA", "categoria": "VENDA", "lancar": True, "lancado": False,
        })
        self.assertTrue(ok)
        self.assertIn("PARA LANCAR", msg)
        self.assertIn("1004", msg)

    def test_integrado_bloqueado_mostra_observacao(self):
        ok, msg = interpretar_integracao({
            "status": "INTEGRADO", "oidDocumento": 9, "naView": True, "lancar": False,
            "lancado": False, "observacao": "Categoria TRANSFERÊNCIA não possui rotina",
        })
        self.assertTrue(ok)
        self.assertIn("BLOQUEADO", msg)
        self.assertIn("TRANSFERÊNCIA", msg)

    def test_ja_integrado_e_lancado(self):
        ok, msg = interpretar_integracao(
            {"status": "JA_INTEGRADO", "oidDocumento": 9, "naView": True, "lancado": True, "miro": "5100"})
        self.assertTrue(ok)
        self.assertIn("MIRO 5100", msg)

    def test_fora_da_view(self):
        ok, msg = interpretar_integracao(
            {"status": "INTEGRADO", "oidDocumento": 9, "naView": False, "observacao": "fornecedor sem cadastro"})
        self.assertTrue(ok)
        self.assertIn("fornecedor sem cadastro", msg)

    def test_falhas_de_negocio(self):
        for status in ("NAO_INTEGRADO", "ERRO_LINCROS", "XML_INVALIDO"):
            ok, msg = interpretar_integracao({"status": status, "detalhes": "motivo X"})
            self.assertFalse(ok)
            self.assertIn(status, msg)
            self.assertIn("motivo X", msg)


class EnviarXmlsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.arqs = []
        for nome in ("a.xml", "b.xml"):
            p = Path(self._tmp.name) / nome
            p.write_bytes(b"<x/>")
            self.arqs.append(p)

    def test_upload_padrao_usa_rota_de_upload(self):
        api = ApiFalsa(upload=_upload({"oidCte": "1", "protocolo": 2, "status": "CONFIRMADO"}))
        res = enviar_xmls(api, self.arqs)
        self.assertEqual([r.ok for r in res], [True, True])
        self.assertEqual({c[0] for c in api.chamadas}, {"upload"})

    def test_forcar_usa_rota_de_integracao(self):
        api = ApiFalsa(forcar={"status": "INTEGRADO", "oidDocumento": 1, "naView": True, "lancar": True,
                               "lancado": False, "centro": "1004", "tipo": "DESPESA", "categoria": "VENDA"})
        res = enviar_xmls(api, self.arqs, forcar_integracao=True)
        self.assertTrue(all(r.ok for r in res))
        self.assertEqual({c[0] for c in api.chamadas}, {"forcar"})

    def test_excecao_vira_falha_sem_derrubar_o_lote(self):
        api = ApiFalsa(forcar=lambda n: ApiError("rota inexistente", 404) if n == "a.xml" else
                       {"status": "INTEGRADO", "oidDocumento": 1, "naView": False})
        res = enviar_xmls(api, self.arqs, forcar_integracao=True)
        self.assertEqual([r.ok for r in res], [False, True])
        self.assertIn("rota inexistente", res[0].resposta)

    def test_parar_interrompe(self):
        api = ApiFalsa(upload=_upload({"oidCte": "1", "status": "CONFIRMADO"}))
        res = enviar_xmls(api, self.arqs, should_stop=lambda: True)
        self.assertEqual(res, [])


if __name__ == "__main__":
    unittest.main()
