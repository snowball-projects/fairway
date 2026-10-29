import {CatalogRead as PublishedCatalogRead} from '../src/fairway/static/catalog-read.mjs';
import {catalogIndexes} from '../scripts/catalog-indexes.mjs';
export {sortCourses} from '../scripts/catalog-indexes.mjs';
export function publishedCatalog(value) {
 const keyed=(rows,key)=>Object.fromEntries(rows.map(row=>[row[key],row]));
 return {...value,indexes:catalogIndexes(value),facilities:keyed(value.facilities,'facility_id'),courses:keyed(value.courses,'course_id'),destinations:keyed(value.destinations||[],'id')};
}
export class CatalogRead extends PublishedCatalogRead {
  constructor(value){super(publishedCatalog(value));}
}
