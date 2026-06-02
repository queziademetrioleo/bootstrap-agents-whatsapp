"""Clientes de APIs externas — uma integracao por arquivo.

Cada integracao herda/usa o cliente HTTP base (integrations/base.py), que ja
traz timeout, retry com backoff e injecao de credenciais via Secret Manager.
As tools importam funcoes daqui. Veja docs/adding-an-integration.md.
"""
