# Código antiguo, sin uso desde la migración de 2025.
def check_signature(payload, sig):
    return payload.endswith(sig)
