import {CatalogRead as PublishedCatalogRead} from '../src/fairway/static/catalog-read.mjs';
import {catalogIndexes} from '../scripts/catalog-indexes.mjs';
export {sortCourses} from '../scripts/catalog-indexes.mjs';
export function publishedCatalog(value) {
 return {...value,indexes:catalogIndexes(value)};
}
export class CatalogRead extends PublishedCatalogRead {
  constructor(value){super(publishedCatalog(value));}
}
