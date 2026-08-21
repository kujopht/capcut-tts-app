"use client";

/**
 * Luu du an Subtitle Studio CUC BO (Phan 4H) — IndexedDB, KHONG BAO GIO gui
 * len backend. Chi luu METADATA NHE: phan doan phu de, ngon ngu, ten/kich
 * thuoc video de nguoi dung nhan lai dung tep — TUYET DOI khong luu chinh
 * video (co the vai GB) vao day.
 *
 * MOT object store duy nhat ("projects"), khoa la `id` do nguoi dung dat
 * (ten du an) — don gian hoa co chu dich, day khong phai mot he CSDL da
 * bang.
 */

import type { SubtitleSegment } from "./model";

const DB_NAME = "fanfic-subtitle-studio";
const DB_VERSION = 1;
const STORE = "projects";

export interface SubtitleProject {
  id: string;
  name: string;
  updatedAt: string;
  segments: SubtitleSegment[];
  /** Ten/kich thuoc/thoi luong video — CHI de nhan dien, KHONG phai chinh
      tep video (xem docstring dau file). */
  videoFingerprint: {
    fileName: string;
    sizeBytes: number;
    durationSeconds: number;
  } | null;
  targetLanguage: string;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function luuDuAn(project: SubtitleProject): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(project);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function docDuAn(id: string): Promise<SubtitleProject | null> {
  const db = await openDb();
  const ra = await new Promise<SubtitleProject | null>((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(id);
    req.onsuccess = () => resolve(req.result ?? null);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return ra;
}

export async function danhSachDuAn(): Promise<SubtitleProject[]> {
  const db = await openDb();
  const ra = await new Promise<SubtitleProject[]>((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result ?? []);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return ra.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export async function xoaDuAn(id: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}
