import unittest
from datetime import date, datetime

from pydosap.formatting import (
    data_br, extrair_chaves, find_document_number, moeda_brl, parse_date, parse_sap_number,
    sap_date, sap_money, to_sap,
)
from pydosap.models import ControleLancamento, FiltroCTE


class FormattingTests(unittest.TestCase):
    def test_to_sap(self):
        self.assertEqual(to_sap(None), "")
        self.assertEqual(to_sap(1500000), "1500000")
        self.assertEqual(to_sap(10.0), "10")
        self.assertEqual(to_sap(0.5), "0,5")
        self.assertEqual(to_sap("FM"), "FM")

    def test_sap_money(self):
        self.assertEqual(sap_money(1234.5), "1234,50")
        self.assertEqual(sap_money(None), "0,00")
        self.assertEqual(sap_money("99.999"), "100,00")

    def test_parse_sap_number(self):
        self.assertEqual(parse_sap_number("0,00"), 0.0)
        self.assertEqual(parse_sap_number("1.234,56"), 1234.56)
        self.assertEqual(parse_sap_number("1.234,56-"), -1234.56)
        self.assertEqual(parse_sap_number(""), 0.0)
        with self.assertRaises(ValueError):
            parse_sap_number("abc")

    def test_datas(self):
        self.assertEqual(sap_date("2026-09-01T10:30:00-03:00"), "01.09.2026")
        self.assertEqual(sap_date("2026-09-01"), "01.09.2026")
        self.assertEqual(sap_date("01/09/2026"), "01.09.2026")
        self.assertEqual(sap_date(date(2026, 9, 1)), "01.09.2026")
        self.assertEqual(sap_date(datetime(2026, 9, 1, 8)), "01.09.2026")
        self.assertEqual(sap_date(""), "")
        self.assertEqual(sap_date(None), "")
        with self.assertRaises(ValueError):
            parse_date("ontem")

    def test_find_document_number(self):
        self.assertEqual(find_document_number("Ped.padrão criado sob o número 4500123456"), "4500123456")
        self.assertEqual(find_document_number("Documento 5105123456 foi registrado"), "5105123456")
        self.assertEqual(find_document_number("Sem número 123"), "")
        self.assertEqual(find_document_number("12345678901"), "")  # 11 dígitos: não é documento


class ChavesTests(unittest.TestCase):
    def test_extrair_chaves(self):
        validas, ignoradas = extrair_chaves("111\n222, 333;111  444'x  55\"; DROP")
        self.assertEqual(validas, ["111", "222", "333", "DROP"])
        self.assertEqual(ignoradas, ["444'x", "55\""])
        self.assertEqual(extrair_chaves(None), ([], []))


class ModelsTests(unittest.TestCase):
    def test_filtro_payload_vazio(self):
        self.assertEqual(FiltroCTE().to_payload(), {"filtros": {}})

    def test_filtro_payload_completo(self):
        f = FiltroCTE(
            regiao=" NE ", centro="2005", data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 15),
            somente_nao_lancados=True, somente_validados=True, chaves=["1", "2"],
        )
        self.assertEqual(f.to_payload(), {"filtros": {
            "regiao": "NE", "centro": "2005", "dataInicio": "2026-09-01", "dataFim": "2026-09-15",
            "somenteNaoLancados": True, "somenteValidados": True, "chaves": ["1", "2"],
        }})

    def test_controle_data_iso(self):
        self.assertEqual(ControleLancamento().data_lancamento_iso, "")
        self.assertEqual(ControleLancamento(data_lancamento=date(2026, 9, 18)).data_lancamento_iso, "2026-09-18")


if __name__ == "__main__":
    unittest.main()


class DataBrMoedaBrlTests(unittest.TestCase):
    def test_data_br(self):
        self.assertEqual(data_br("2026-09-18T00:00:00"), "18/09/2026")
        self.assertEqual(data_br("2026-09-18"), "18/09/2026")
        self.assertEqual(data_br(""), "")
        self.assertEqual(data_br(None), "")

    def test_moeda_brl(self):
        self.assertEqual(moeda_brl(1234.5), "R$ 1.234,50")
        self.assertEqual(moeda_brl(0), "R$ 0,00")
        self.assertEqual(moeda_brl(""), "")
        self.assertEqual(moeda_brl(None), "")
