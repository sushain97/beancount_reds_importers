"""Fidelity All Accounts .csv importer."""

import re

# from beangulp import cache

from beancount_reds_importers.libreader import csvreader
from beancount_reds_importers.libtransactionbuilder import investments


class Importer(csvreader.Importer, investments.Importer):
    IMPORTER_NAME = "Fidelity All Accounts CSV"

    def custom_init(self):
        self.max_rounding_error = 0.04
        self.filename_pattern_def = ".*_Transactions_"
        self.header_identifier = ""
        self.column_labels_line = (
            'Run Date,Account,Account Number,Action,Symbol,Description,Type,Exchange Quantity,Exchange Currency,Currency,Price,Quantity,Exchange Rate,Commission,Fees,Accrued Interest,Amount,Settlement Date'
        )
        self.get_ticker_info = self.get_ticker_info_from_id
        self.date_format = "%m/%d/%Y"
        self.funds_db_txt = "funds_by_ticker"
        # self.get_payee = lambda ot: ot.Action
        # fmt: off
        self.header_map = {
            "Account Number": "account_number",
            "Run Date": "date",
            "Action": "memo",
            "Symbol": "security",
            "Quantity": "units",
            "Accrued Interest": "accrued_interest",
            "Price": "unit_price",
            "Amount": "amount",
            "Settlement Date": "settleDate",
            "Fees": "fees",
            "Commission": "commission",
        }
        self.transaction_type_map = {
            "REINVESTMENT": "buymf",
            "REDEMPTION FROM": "sellmf",
            "DIVIDEND RECEIVED": "dividends",
            "TRANSFERRED FROM": "cash",
            "YOU BOUGHT": "buystock",
            "YOU SOLD": "sellstock",
            "DIRECT DEPOSIT": "dep",
            "TRANSFERRED TO": "xfer",
            "MUNI EXEMPT": "income",
            "INTEREST EARNED": "income",
            "FEE CHARGED": "fee",
            "FOREIGN TAX": "fee",
            "BILL PAYMENT": "payment",
            "DEBIT CARD": "payment",
            "DIRECT DEBIT": "payment",
            "CHECK RECEIVED": "dep",
        }
        self.skip_transaction_types = []
        self.security_symbol_map = {
            # if you have securities where you use a custom symbol
            # instead of the one to be found in the CSV, example would
            # be singhle letter symbols which cannot be a bc commodity name
            "M": "M-M",
            "V": "V-V",
            "T": "T-T",
            "C": "C-C",
            "F": "F-F",
            "G": "G-G",
            "K": "K-K",
            "A": "A-A",
        }
        # fmt: on

    def deep_identify(self, file):
        return (
            re.match(self.header_identifier, file.head(), flags=re.DOTALL)
        )

    def skip_transaction(self, ot):
        return ot.type in ["", "Journal"]

    def prepare_table(self, rdr):
        if "" in rdr.fieldnames():
            rdr = rdr.cutout("")  # clean up last column

        def cusip_to_symbols(s):
            """
            Stocks and mutual funds are represented by their
            symbol, but bonds and core account funds (some?) use
            their cusip, try to convert these to symbol if they
            are present in fund_data
            """
            return self.funds_by_id.get(s, (s,))[0]

        def map_symbols(s):
            """
            Stocks and mutual funds are represented by their
            symbol, but bonds and core account funds (some?) use
            their cusip, try to convert these to symbol if they
            are present in fund_data
            """
            return self.security_symbol_map.get(s, s)

        rdr = rdr.convert("Symbol", cusip_to_symbols)
        rdr = rdr.convert("Symbol", map_symbols)

        rdr = rdr.convert("Symbol", "", where=lambda r: r.Action.startswith("INTEREST EARNED FDIC INSURED DEPOSIT AT"))

        rdr = rdr.addfield("total", lambda x: x["Amount"])
        rdr = rdr.addfield("tradeDate", lambda x: x["Run Date"])

        # the REINVESTMENT action will include a fund symbol as the 2nd word,
        # so only use the first word for mapping
        rdr = rdr.capture("Action", "(REINVESTMENT|\\S+(?:\\s+\\S+)?)", ["type"], include_original=True)

        return rdr
