import test from "node:test";
import assert from "node:assert/strict";
import { isHeicPhoto } from "../photo-format.js";

test("HEIC detection uses filename, MIME type, and image file signature", async () => {
  assert.equal(await isHeicPhoto(new File(["not decoded"], "photo.HEIC", { type: "application/octet-stream" })), true);
  assert.equal(await isHeicPhoto(new File(["not decoded"], "photo", { type: "image/heif" })), true);
  const isoBmff = new Uint8Array(32);
  isoBmff.set(new TextEncoder().encode("ftypheix"), 4);
  assert.equal(await isHeicPhoto(new File([isoBmff], "photo", { type: "application/octet-stream" })), true);
  assert.equal(await isHeicPhoto(new File(["plain text"], "photo", { type: "application/octet-stream" })), false);
});
