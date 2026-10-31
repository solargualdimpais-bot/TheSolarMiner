export function normalizeFavoriteIds(value){
  return [...new Set((Array.isArray(value)?value:[]).filter(id=>typeof id==="string"&&id.trim()))];
}

export function addFavoriteId(value,id){
  const clean=String(id||"").trim();
  return clean?[...new Set([...normalizeFavoriteIds(value),clean])]:normalizeFavoriteIds(value);
}

export function reorderFavoriteIds(value,visibleOrder){
  const all=normalizeFavoriteIds(value),visible=normalizeFavoriteIds(visibleOrder),visibleSet=new Set(visible);
  let nextIndex=0;
  const reordered=all.map(id=>visibleSet.has(id)?visible[nextIndex++]:id);
  for(const id of visible)if(!all.includes(id))reordered.push(id);
  return reordered;
}
