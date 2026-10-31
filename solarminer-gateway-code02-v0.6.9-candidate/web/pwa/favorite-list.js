export function normalizeFavoriteIds(value){
  return [...new Set((Array.isArray(value)?value:[]).filter(id=>typeof id==="string"&&id.trim()))];
}

export function addFavoriteId(value,id){
  const clean=String(id||"").trim();
  return clean?[...new Set([...normalizeFavoriteIds(value),clean])]:normalizeFavoriteIds(value);
}
