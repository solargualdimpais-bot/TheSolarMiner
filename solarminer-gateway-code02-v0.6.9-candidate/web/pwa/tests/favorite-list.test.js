import test from "node:test";
import assert from "node:assert/strict";
import {addFavoriteId,normalizeFavoriteIds,reorderFavoriteIds} from "../favorite-list.js";

test("favorite list accepts more than two unique devices without truncation",()=>{
  const ids=Array.from({length:24},(_,index)=>`device-${index+1}`);
  assert.deepEqual(normalizeFavoriteIds(ids),ids);
  assert.equal(addFavoriteId(ids,"device-25").length,25);
});

test("favorite list de-duplicates additions and retains temporarily unavailable device ids",()=>{
  assert.deepEqual(addFavoriteId(["device-a","device-b","device-c"],"device-b"),["device-a","device-b","device-c"]);
  assert.deepEqual(normalizeFavoriteIds(["device-a","missing-device","device-a",null]),["device-a","missing-device"]);
});

test("favorite drag order persists while unavailable devices keep their slots",()=>{
  assert.deepEqual(reorderFavoriteIds(["a","missing","b","c"],["c","a","b"]),["c","missing","a","b"]);
});
