from equities.fund import Fund


def test_fund_protocol_is_runtime_checkable():
    class FakeFund:
        name = "equity"
        def positions(self):
            return []
        def pnl(self):
            return 0.0
        def exposure(self):
            return 0.0
        def set_allocation(self, usd):
            self._alloc = usd
    f = FakeFund()
    assert isinstance(f, Fund)
    f.set_allocation(500.0)
    assert f._alloc == 500.0


def test_object_missing_method_is_not_a_fund():
    class NotAFund:
        name = "x"
    assert not isinstance(NotAFund(), Fund)
