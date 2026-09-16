import { NextResponse } from "next/server";
import * as fs from 'fs';
import * as path from 'path';

export async function GET() {
  const mapPath = path.join(process.cwd(), 'configs', 'warehouse_map.json');
  const mapData = JSON.parse(fs.readFileSync(mapPath, 'utf-8'));
  return NextResponse.json(mapData);
}