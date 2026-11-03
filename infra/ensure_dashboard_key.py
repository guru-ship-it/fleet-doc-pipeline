"""Give an existing demo secret a DASHBOARD_KEY (the dashboard access code) if it has none, and print the code.
The code is meant to be shared with the people who view the dashboard. Every other value in the secret is read and
written back unchanged and is never printed. Redeploy afterwards: functions load the secret once per container.

    python infra/ensure_dashboard_key.py
"""
import json
import secrets

import boto3

REGION, SECRET = "ap-south-1", "fleet-doc-pipeline/demo"
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"      # easy to read out and type: no 0/o, 1/l/i


def main() -> None:
    sm = boto3.client("secretsmanager", region_name=REGION)
    values = json.loads(sm.get_secret_value(SecretId=SECRET)["SecretString"])
    code = values.get("DASHBOARD_KEY")
    if code and code != "PASTE_HERE":
        print("DASHBOARD_KEY already set. Access code: %s" % code)
        return
    code = "fleet-" + "".join(secrets.choice(ALPHABET) for _ in range(10))
    values["DASHBOARD_KEY"] = code
    sm.put_secret_value(SecretId=SECRET, SecretString=json.dumps(values))
    print("DASHBOARD_KEY added (keys now: %s). Access code: %s" % (", ".join(sorted(values)), code))


if __name__ == "__main__":
    main()
