from __future__ import annotations

from dataclasses import replace

from okx_client import OkxApiError, OkxRestClient, load_env


def main() -> None:
    load_env()
    client = OkxRestClient.from_env()

    print("Checking OKX public REST...")
    server_time = client.get_server_time()
    print(f"OKX server time: {server_time}")

    ticker = client.get_ticker("BTC-USDT")
    last_price = ticker.get("data", [{}])[0].get("last")
    print(f"BTC-USDT last price: {last_price}")

    if not all((client.api_key, client.secret_key, client.passphrase)):
        print("Skipping private API check: fill OKX_API_KEY, OKX_SECRET_KEY, and OKX_PASSPHRASE in .env first.")
        return

    print("Checking OKX private REST authentication...")
    client, account_config = get_account_config_with_environment_hint(client)
    config = account_config.get("data", [{}])[0]
    print(
        "Private API OK. "
        f"acctLv={config.get('acctLv')} "
        f"posMode={config.get('posMode')} "
        f"simulated={client.simulated_trading}"
    )

    balance = client.get_balance()
    details = balance.get("data", [{}])[0].get("details", [])
    non_zero = [
        item
        for item in details
        if item.get("cashBal") not in (None, "", "0", "0.0", "0.00")
    ]
    print(f"Balance currencies returned: {len(details)}")
    if non_zero:
        print("Non-zero balances:")
        for item in non_zero[:10]:
            print(f"  {item.get('ccy')}: cashBal={item.get('cashBal')} availBal={item.get('availBal')}")


def get_account_config_with_environment_hint(
    client: OkxRestClient,
) -> tuple[OkxRestClient, dict]:
    try:
        return client, client.get_account_config()
    except OkxApiError as exc:
        if exc.okx_code != "50101":
            raise

        alternate = replace(client, simulated_trading=not client.simulated_trading)
        try:
            response = alternate.get_account_config()
        except OkxApiError:
            raise exc

        expected = "1" if alternate.simulated_trading else "0"
        environment = "demo/simulated" if alternate.simulated_trading else "production/live"
        print(
            "API key environment mismatch fixed by retrying "
            f"{environment}. Set OKX_SIMULATED_TRADING={expected} in .env."
        )
        return alternate, response


if __name__ == "__main__":
    try:
        main()
    except OkxApiError as exc:
        print(f"Connection failed: {exc}")
        if exc.response is not None:
            print(f"Response: {exc.response}")
        raise SystemExit(1)
