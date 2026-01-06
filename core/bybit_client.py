def get_closed_pnl(self, symbol, limit=1):
        try:
            response = self.session.get_closed_pnl(
                category="linear",
                symbol=symbol,
                limit=limit
            )
            if response['retCode'] == 0:
                return response['result']['list']
            return []
        except Exception as e:
            print(f"Error obteniendo PnL cerrado: {e}")
            return []
