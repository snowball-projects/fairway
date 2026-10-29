// Build-only ordering and lookup positions for the published browser details.
import {recordLabel} from '../src/fairway/static/catalog-read.mjs';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';

export function sortCourses(courses,sort='name') {
  const value=c=>sort==='holes'?(Number.isFinite(c.physical_holes)?c.physical_holes:null):null;
  const label=c=>recordLabel(c,c.course_id?'course':'facility');
  return [...courses].sort((a,b)=>{
    if(sort==='name')return label(a).localeCompare(label(b),'en-US') || (a.course_id??a.facility_id).localeCompare(b.course_id??b.facility_id,'en-US');
    const av=value(a),bv=value(b);return av===null?(bv===null?label(a).localeCompare(label(b),'en-US'):1):bv===null?-1:av-bv||label(a).localeCompare(label(b),'en-US');
  });
}
export function catalogIndexes({facilities,courses,destinations=[]}) {
  const entries=[...courses,...facilities],at=new Map(entries.map((row,i)=>[row,i]));
  const coursesByFacility=new Map();
  for(const [i,course] of courses.entries()) {
    const group=coursesByFacility.get(course.facility_id)||[];
    group.push(i);coursesByFacility.set(course.facility_id,group);
  }
  const eligible=[...courses,...facilities.filter(f=>!coursesByFacility.has(f.facility_id))];
  const browse={};
  for(const sort of ['name','holes']) {
    const ordered=sortCourses(eligible,sort),groups=new Map(),independent=[];
    for(const record of ordered) {
      if(record.facility_id===null)independent.push(at.get(record));
      if(!record.course_id||!record.facility_id||coursesByFacility.get(record.facility_id).length<2)continue;
      const group=groups.get(record.facility_id)||[];
      group.push(at.get(record));groups.set(record.facility_id,group);
    }
    browse[sort]={entries:ordered.map(row=>at.get(row)),groups:[...groups],independent};
  }
  return {coursesByFacility:[...coursesByFacility],browse,
    mapCourses:courses.flatMap((c,i)=>c.facility_id===null?[i]:[])};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)
  process.stdout.write(JSON.stringify(catalogIndexes(JSON.parse(readFileSync(0,'utf8')))));
