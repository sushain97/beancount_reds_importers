"""Fidelity All Accounts .csv importer."""

import re
import math

# from beangulp import cache

from beancount_reds_importers.libreader import csvreader
from beancount_reds_importers.libtransactionbuilder import investments


class Importer(csvreader.Importer, investments.Importer):
    IMPORTER_NAME = "Fidelity All Accounts CSV"

    def custom_init(self):
        self.max_rounding_error = 0.04
        self.file_encoding = "utf-8-sig"
        self.filename_pattern_def = "Accounts_History.*"
        self.header_identifier = "^Run Date,Account,Account Number,Action,Symbol.*"
        self.column_labels_line = "Run Date,Account,Account Number,Action,Symbol,Description,Type,Exchange Quantity,Exchange Currency,Currency,Price,Quantity,Exchange Rate,Commission,Fees,Accrued Interest,Amount,Settlement Date"
        self.get_ticker_info = self.get_ticker_info_from_id
        self.date_format = "%m/%d/%Y"
        self.funds_db_txt = "funds_by_ticker"
        self.used_inferred_price = (
            True  # calculate price to 4 decimal places rather than using csv price
        )
        # fmt: off
        self.header_map = {
            "Account Number": "account_number",
            "Run Date": "date",
            "Action": "memo",
            "Symbol": "security",
            "Quantity": "units",
            "Accrued Interest": "accrued_interest",
            "Amount": "amount",
            "Settlement Date": "settleDate",
            "Fees": "fees",
            "Commission": "commission",
        }
        if getattr(self, "used_inferred_price", False):
            self.header_map["inferred_price"] = "unit_price"
        else:
            self.header_map["Price"] = "unit_price"

        self.transaction_type_map = {
            "REINVESTMENT": "buymf",
            "REDEMPTION FROM": "sellmf",
            "DIVIDEND RECEIVED": "dividends",
            "TRANSFERRED FROM": "cash",
            "YOU BOUGHT": "buystock",
            "YOU SOLD": "sellstock",
            "REDEMPTION PAYOUT": "sellother",
            "DIRECT DEPOSIT": "dep",
            "TRANSFERRED TO": "xfer",
            "MUNI EXEMPT": "income",
            "INTEREST EARNED": "income",
            "FEE CHARGED": "fee",
            "ADVISOR FEE": "fee",
            "FOREIGN TAX": "fee",
            "BILL PAYMENT": "payment",
            "DEBIT CARD": "payment",
            "Check Paid": "payment",
            "DIRECT DEBIT": "payment",
            "Electronic Funds": "payment",
            "CHECK RECEIVED": "dep",
            "CASH ADVANCE": "debit",
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
        return re.search(self.header_identifier, file.head(), flags=re.MULTILINE)

    def skip_transaction(self, ot):
        if ot.account_number != self.config["account_number"]:
            return True
        if ot.type in ["MERGER MER", "ADJUST FEE", "DISTRIBUTION"]:
            # this sort of transaction must be handled manually
            # ADJUST FEE sounds like a fee, but has been used for a 1:1 reorg
            # DISTRIBUTION is for splits
            return True

        return False

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

        # add an inferred price column b/c csv prices are only to two decimals
        rdr = rdr.addfield(
            "inferred_price",
            lambda row: str(
                round(-1 * float(row["Amount"]) / float(row["Quantity"]), 4)
            )
            if not math.isclose(
                float(row["Quantity"]),
                0,
                rel_tol=1e-09,
                abs_tol=1e-09,
            )
            else "",
        )

        rdr = rdr.convert(
            "Symbol",
            "",
            where=lambda r: r.Action.startswith(
                "INTEREST EARNED FDIC INSURED DEPOSIT AT"
            ),
        )

        rdr = rdr.addfield("total", lambda x: x["Amount"])
        rdr = rdr.addfield("tradeDate", lambda x: x["Run Date"])

        # the REINVESTMENT action will include a fund symbol as the 2nd word,
        # so only use the first word for mapping
        # DISTRIBUTION which is used for splits will also include a symbol as
        # 2nd word
        rdr = rdr.capture(
            "Action",
            "(DISTRIBUTION|REINVESTMENT|\\S+(?:\\s+\\S+)?)",
            ["type"],
            include_original=True,
        )

        return rdr
