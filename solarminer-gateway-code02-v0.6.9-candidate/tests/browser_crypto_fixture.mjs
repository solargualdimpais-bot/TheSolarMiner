import { generateDeviceIdentity, signText, pairDevice, loginDevice, logoutDevice } from "../web/pwa/auth-client.js";

const input = JSON.parse(await new Promise((resolve, reject) => {
  let value = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", chunk => value += chunk);
  process.stdin.on("end", () => { try { resolve(value); } catch (error) { reject(error); } });
}));

if (input.mode === "pair") {
  const identity = await generateDeviceIdentity();
  const canonical = `PAIR\n${input.code}\n${identity.publicKeyDigest}\n${input.mac.toUpperCase()}\n${input.timestamp}\n${input.nonce}`;
  const signature = await signText(identity.privateKey, canonical);
  process.stdout.write(JSON.stringify({ public_key_pem: identity.publicKeyPem, public_key_sha256: identity.publicKeyDigest, signature }));
} else if (input.mode === "sign-login") {
  const pkcs8 = Uint8Array.from(Buffer.from(input.private_key_pkcs8_b64, "base64"));
  const privateKey = await crypto.subtle.importKey("pkcs8", pkcs8, { name: "Ed25519" }, false, ["sign"]);
  process.stdout.write(JSON.stringify({ signature: await signText(privateKey, input.canonical) }));
} else if (input.mode === "flow") {
  const identity = await pairDevice({ baseUrl: input.base_url, pairingCode: input.code, mac: input.mac });
  const session = await loginDevice({ baseUrl: input.base_url, username: input.username, password: input.password, identity });
  const response = await fetch(`${input.base_url}/api/v1/energy/equipment`, {
    headers: { Accept: "application/json", Authorization: `Bearer ${session.access_token}` },
    cache: "no-store", credentials: "omit", redirect: "error"
  });
  const data = await response.json();
  const logout = await logoutDevice({ baseUrl: input.base_url, token: session.access_token });
  process.stdout.write(JSON.stringify({ pair_status: "paired", login_username: session.user.username,
    read_status: response.status, equipment_count: Array.isArray(data.equipment) ? data.equipment.length : null,
    logout_status: logout.status }));
} else {
  throw new Error("unsupported fixture mode");
}
