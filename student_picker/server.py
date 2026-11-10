"""
Web UI Server for student-picker.
Projection-safe, modern dark-mode stage with subtask filtering, real-time toggles,
and session ingestion directly from browser.
"""

import csv
import json
import os
import re
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .core import (
    SessionManager,
    draw_student,
    get_eligible_pool,
    load_session_state,
)
from .ingest import process_submissions_folder

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Student Picker</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #131c2e;
      --card-border: #1e293b;
      --card-hover: #1a263d;
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.25);
      --success: #10b981;
      --danger: #ef4444;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; min-height: 100vh; overflow-x: hidden; }
    .container { max-width: 1140px; margin: 0 auto; }
    
    /* Header */
    header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 18px; border-bottom: 1px solid var(--card-border); gap: 16px; flex-wrap: wrap; }
    .title-group h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; color: #fff; display: flex; align-items: center; gap: 12px; }
    .title-group p { color: var(--text-muted); font-size: 14px; margin-top: 4px; }
    .badge-session { background: #0369a1; color: #e0f2fe; padding: 4px 12px; border-radius: 999px; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
    
    .header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    select, button, input { font-size: 13px; font-weight: 600; cursor: pointer; border: none; border-radius: 10px; transition: all 0.2s ease; }
    select { background: #1e293b; color: #fff; padding: 8px 14px; border: 1px solid var(--card-border); outline: none; }
    .btn-primary { background: #0284c7; color: #fff; padding: 8px 16px; }
    .btn-primary:hover { background: #0369a1; transform: translateY(-1px); }
    .btn-secondary { background: #1e293b; color: var(--text-muted); padding: 8px 14px; border: 1px solid var(--card-border); }
    .btn-secondary:hover { background: #334155; color: #fff; }
    .btn-danger-outline { background: transparent; color: #f87171; border: 1px solid #7f1d1d; padding: 8px 14px; }
    .btn-danger-outline:hover { background: #7f1d1d; color: #fff; }

    /* Tabs */
    .tabs-bar { display: flex; gap: 10px; margin-bottom: 24px; overflow-x: auto; padding-bottom: 4px; }
    .tab-btn {
      flex: 1; min-width: 170px; background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 14px; padding: 14px 18px; text-align: left; position: relative;
    }
    .tab-btn:hover { border-color: #334155; background: var(--card-hover); }
    .tab-btn.active {
      border-color: var(--primary); background: #0c182b;
      box-shadow: 0 0 20px rgba(56, 189, 248, 0.15);
    }
    .tab-btn.active::after {
      content: ''; position: absolute; bottom: 0; left: 16px; right: 16px; height: 3px;
      background: var(--primary); border-radius: 3px 3px 0 0;
    }
    .tab-title { font-size: 15px; font-weight: 700; color: #fff; display: flex; justify-content: space-between; align-items: center; }
    .tab-badge-presented { font-size: 11px; font-weight: 700; background: #064e3b; color: #34d399; padding: 2px 8px; border-radius: 6px; }
    .tab-subtitle { font-size: 12px; color: var(--text-muted); margin-top: 6px; }

    /* Main Grid */
    .main-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 24px; margin-bottom: 24px; }
    @media (max-width: 900px) { .main-grid { grid-template-columns: 1fr; } }

    /* Selector Card */
    .selector-card {
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 20px;
      padding: 36px 28px; display: flex; flex-direction: column; justify-content: center;
      align-items: center; text-align: center; position: relative; min-height: 380px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    }
    
    .status-banner {
      display: none; position: absolute; top: 16px; left: 16px; right: 16px;
      padding: 10px 16px; border-radius: 10px; font-size: 13px; font-weight: 600;
      background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34d399; text-align: center;
    }

    .selector-stage-empty { display: flex; flex-direction: column; align-items: center; gap: 18px; }
    .empty-icon { font-size: 54px; opacity: 0.8; }
    .stage-title { font-size: 20px; font-weight: 700; color: #fff; }
    .stage-desc { font-size: 14px; color: var(--text-muted); max-width: 400px; line-height: 1.5; }

    .btn-draw {
      background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
      color: #fff; font-size: 18px; font-weight: 800; padding: 16px 36px;
      border-radius: 14px; box-shadow: 0 8px 24px rgba(2, 132, 199, 0.35);
      display: flex; align-items: center; gap: 12px; margin-top: 10px;
    }
    .btn-draw:hover { background: linear-gradient(135deg, #0369a1 0%, #075985 100%); transform: translateY(-2px); box-shadow: 0 12px 28px rgba(2, 132, 199, 0.5); }
    .btn-draw:active { transform: translateY(0); }
    .kbd-hint { font-size: 11px; padding: 2px 7px; background: rgba(255,255,255,0.2); border-radius: 6px; font-weight: 700; }

    /* Student Presentation View */
    .drawn-student-box { width: 100%; animation: fadeIn 0.3s ease forwards; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

    .drawn-tag {
      font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.5px;
      color: var(--primary); margin-bottom: 12px; display: inline-flex; align-items: center; gap: 8px;
    }
    .drawn-name {
      font-size: 44px; font-weight: 900; letter-spacing: -0.5px; color: #ffffff;
      line-height: 1.15; margin-bottom: 12px; text-shadow: 0 2px 20px rgba(255,255,255,0.15);
    }
    .drawn-subline { font-size: 14px; color: var(--text-muted); margin-bottom: 20px; }
    
    .drawn-tasks { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; margin-bottom: 28px; }
    .task-pill {
      padding: 8px 16px; border-radius: 999px; font-size: 13px; font-weight: 700;
      display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
      transition: all 0.2s ease; border: 1px solid transparent; user-select: none;
    }
    .task-pill.active-pill {
      background: rgba(56, 189, 248, 0.25); color: #38bdf8; border-color: #38bdf8;
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.35);
    }
    .task-pill.done-pill {
      background: rgba(16, 185, 129, 0.18); color: #34d399; border-color: rgba(16, 185, 129, 0.4);
    }
    .task-pill.done-pill:hover {
      background: rgba(239, 68, 68, 0.2); color: #f87171; border-color: rgba(239, 68, 68, 0.4);
    }
    .task-pill.missing-pill {
      background: rgba(100, 116, 139, 0.15); color: #64748b; border-color: rgba(100, 116, 139, 0.3);
      border-style: dashed;
    }
    .task-pill.missing-pill:hover {
      background: rgba(56, 189, 248, 0.2); color: #38bdf8; border-color: #38bdf8; border-style: solid;
    }

    /* Decision Grid */
    .decision-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; width: 100%; max-width: 540px; margin: 0 auto; }
    .decision-btn {
      padding: 14px 16px; border-radius: 12px; text-align: left; display: flex; flex-direction: column;
      gap: 4px; transition: all 0.15s ease; border: 1px solid transparent;
    }
    .decision-btn strong { font-size: 14px; display: flex; justify-content: space-between; align-items: center; }
    .decision-btn span { font-size: 12px; opacity: 0.8; }
    
    .btn-rule-pass { background: #064e3b; color: #6ee7b7; border-color: #059669; }
    .btn-rule-pass:hover { background: #047857; color: #fff; transform: translateY(-1px); }
    
    .btn-rule-fail { background: #451a03; color: #fcd34d; border-color: #b45309; }
    .btn-rule-fail:hover { background: #78350f; color: #fff; transform: translateY(-1px); }
    
    .btn-rule-strike { background: #450a0a; color: #fca5a5; border-color: #b91c1c; }
    .btn-rule-strike:hover { background: #7f1d1d; color: #fff; transform: translateY(-1px); }
    
    .btn-rule-excuse { background: #1e293b; color: #cbd5e1; border-color: #334155; }
    .btn-rule-excuse:hover { background: #334155; transform: translateY(-1px); }

    /* Side Stats Card */
    .side-card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 20px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.3); }
    .side-header { font-size: 16px; font-weight: 700; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }
    .stat-row { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--card-border); font-size: 14px; }
    .stat-label { color: var(--text-muted); display: flex; align-items: center; gap: 8px; }
    .stat-val { font-weight: 800; font-size: 16px; color: #fff; }

    .rule-brief { margin-top: 20px; background: #090d16; border: 1px solid var(--card-border); border-radius: 12px; padding: 14px; font-size: 12px; color: var(--text-muted); line-height: 1.6; }
    .rule-brief strong { color: var(--text); }

    /* Roster Table */
    .roster-card { margin-top: 24px; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 20px; padding: 24px; }
    .roster-controls { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; gap: 16px; flex-wrap: wrap; }
    .search-box { background: #090d16; border: 1px solid var(--card-border); border-radius: 8px; padding: 8px 14px; font-size: 13px; color: #fff; width: 230px; outline: none; }
    .search-box:focus { border-color: var(--primary); }

    .filter-pills-row { display: flex; gap: 8px; align-items: center; margin-bottom: 16px; font-size: 12px; color: var(--text-muted); flex-wrap: wrap; }
    .filter-pill {
      background: #090d16; border: 1px solid var(--card-border);
      color: var(--text-muted); padding: 5px 12px; border-radius: 999px;
      font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.15s ease;
    }
    .filter-pill.active { background: var(--primary); color: #000; border-color: var(--primary); }
    .filter-pill:hover:not(.active) { background: #1a2538; color: #fff; }

    .subtask-badges-wrap { display: inline-flex; align-items: center; gap: 5px; flex-wrap: wrap; }
    .task-badge-btn {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700;
      cursor: pointer; transition: all 0.15s ease; border: 1px solid transparent; user-select: none;
    }
    .task-badge-btn.active {
      background: rgba(16, 185, 129, 0.16); color: #34d399; border-color: rgba(16, 185, 129, 0.35);
    }
    .task-badge-btn.active:hover {
      background: rgba(239, 68, 68, 0.2); color: #f87171; border-color: rgba(239, 68, 68, 0.4);
      transform: translateY(-1px);
    }
    .task-badge-btn.inactive {
      background: rgba(100, 116, 139, 0.12); color: #64748b; border-color: rgba(100, 116, 139, 0.25); opacity: 0.75;
    }
    .task-badge-btn.inactive:hover {
      background: rgba(56, 189, 248, 0.2); color: #38bdf8; border-color: #38bdf8; opacity: 1; transform: translateY(-1px);
    }
    .badge-total-count {
      font-size: 10px; font-weight: 800; padding: 3px 6px; border-radius: 4px;
      background: #090d16; border: 1px solid var(--card-border); color: var(--text-muted); margin-left: 2px;
    }

    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; padding: 12px 14px; background: #090d16; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--card-border); }
    td { padding: 12px 14px; border-bottom: 1px solid #1a2538; vertical-align: middle; }
    tr:hover td { background: var(--card-hover); }
    
    .badge-status { padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
    .status-tag-eligible { background: #064e3b; color: #6ee7b7; }
    .status-tag-presented { background: #1e3a8a; color: #93c5fd; }
    .status-tag-strike { background: #7f1d1d; color: #fca5a5; }
    .status-tag-excused { background: #1e293b; color: #94a3b8; }

    /* Modals */
    .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); z-index: 200; align-items: center; justify-content: center; }
    .modal-card { background: #131c2e; border: 1px solid #1e293b; border-radius: 18px; padding: 28px; max-width: 520px; width: 92%; box-shadow: 0 20px 40px rgba(0,0,0,0.6); animation: modalPop 0.2s ease forwards; text-align: left; }
    @keyframes modalPop { 0% { opacity: 0; transform: scale(0.95); } 100% { opacity: 1; transform: scale(1); } }
    .modal-title { font-size: 20px; font-weight: 800; color: #fff; margin-bottom: 8px; }
    .modal-body { font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 20px; }
    .modal-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }
    
    /* Ingest Form Inputs */
    .form-group { margin-bottom: 14px; }
    .form-label { display: block; font-size: 12px; font-weight: 700; color: #cbd5e1; margin-bottom: 6px; }
    .form-input { width: 100%; background: #090d16; border: 1px solid var(--card-border); color: #fff; padding: 9px 12px; border-radius: 8px; font-size: 13px; outline: none; }
    .form-input:focus { border-color: var(--primary); }

    #toast { position: fixed; bottom: 24px; right: 24px; background: #0284c7; color: #fff; padding: 12px 22px; border-radius: 12px; font-size: 14px; font-weight: 600; box-shadow: 0 10px 25px rgba(0,0,0,0.5); opacity: 0; pointer-events: none; transition: all 0.25s ease; z-index: 100; transform: translateY(10px); }
    #toast.show { opacity: 1; pointer-events: auto; transform: translateY(0); }
    #confettiCanvas { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; pointer-events: none; z-index: 99; }
  </style>
</head>
<body>
<canvas id="confettiCanvas"></canvas>
<div id="toast">Action Recorded</div>

<!-- Subtask Warning Modal -->
<div class="modal-overlay" id="subtaskWarningModal">
  <div class="modal-card" style="text-align:center; max-width:440px; border-color:#f59e0b;">
    <div style="font-size:38px; margin-bottom:12px;">⚠️</div>
    <div class="modal-title" style="color:#f59e0b;">Subtask Already Presented</div>
    <div class="modal-body" id="modalBody">
      This subtask was already successfully presented. Do you want to select another student anyway?
    </div>
    <div class="modal-actions" style="justify-content:center;">
      <button class="btn-secondary" onclick="closeWarningModal()">Cancel</button>
      <button class="btn-primary" style="background:#d97706;" onclick="confirmDrawAgain()">Yes, Draw Again</button>
    </div>
  </div>
</div>

<!-- Ingest / Load Session Modal -->
<div class="modal-overlay" id="ingestModal">
  <div class="modal-card">
    <div class="modal-title">📂 Ingest Submissions / Load Session</div>
    <div class="modal-body">
      Select an LMS spreadsheet (Excel/CSV) and optional blank notebook template to automatically analyze student submissions:
    </div>

    <div class="form-group">
      <label class="form-label">Session Name (e.g. exercise_2)</label>
      <input type="text" class="form-input" id="ingestSessionName" placeholder="exercise_2">
    </div>

    <div class="form-group">
      <label class="form-label">LMS Submissions File Path (.xlsx or .csv)</label>
      <input type="text" class="form-input" id="ingestLmsPath" placeholder="/path/to/Exercise 2.xlsx">
    </div>

    <div class="form-group">
      <label class="form-label">Blank Base Notebook (.ipynb, optional for diffing)</label>
      <input type="text" class="form-input" id="ingestBasePath" placeholder="/path/to/exercise2_data.ipynb">
    </div>

    <div style="display:grid; grid-template-columns:1fr 2fr; gap:12px;">
      <div class="form-group">
        <label class="form-label">Group (Optional)</label>
        <input type="number" class="form-input" id="ingestGroupNum" placeholder="6">
      </div>
      <div class="form-group">
        <label class="form-label">Roster CSV (Optional)</label>
        <input type="text" class="form-input" id="ingestRosterPath" placeholder="/path/to/group_roster.csv">
      </div>
    </div>

    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeIngestModal()">Cancel</button>
      <button class="btn-primary" onclick="runIngestFromModal()">🚀 Run Ingest & Load</button>
    </div>
  </div>
</div>

<div class="container">
  <header>
    <div class="title-group">
      <h1>Student Picker <span class="badge-session" id="sessionBadge">Active</span></h1>
      <p>Projection-Safe Presenter Selection & Participation Tracker</p>
    </div>
    <div class="header-actions">
      <select id="sessionSelect" onchange="changeSession(this.value)" title="Select Session"></select>
      <button class="btn-primary" onclick="openIngestModal()">📂 Ingest / Load</button>
      <button class="btn-secondary" onclick="exportReport()">📥 Export CSV</button>
      <button class="btn-danger-outline" onclick="resetSession()">Reset</button>
    </div>
  </header>

  <!-- Subtask Tabs -->
  <div class="tabs-bar">
    <button class="tab-btn active" onclick="switchSubtask('Subtask 1')">
      <div class="tab-title">
        <span>Subtask 1</span>
        <span class="tab-badge-presented" id="pres-Subtask-1" style="display:none;">✓ Presented</span>
      </div>
      <div class="tab-subtitle" id="count-Subtask-1">...</div>
    </button>
    <button class="tab-btn" onclick="switchSubtask('Subtask 2')">
      <div class="tab-title">
        <span>Subtask 2</span>
        <span class="tab-badge-presented" id="pres-Subtask-2" style="display:none;">✓ Presented</span>
      </div>
      <div class="tab-subtitle" id="count-Subtask-2">...</div>
    </button>
    <button class="tab-btn" onclick="switchSubtask('Subtask 3')">
      <div class="tab-title">
        <span>Subtask 3</span>
        <span class="tab-badge-presented" id="pres-Subtask-3" style="display:none;">✓ Presented</span>
      </div>
      <div class="tab-subtitle" id="count-Subtask-3">...</div>
    </button>
    <button class="tab-btn" onclick="switchSubtask('Subtask 4')">
      <div class="tab-title">
        <span>Subtask 4</span>
        <span class="tab-badge-presented" id="pres-Subtask-4" style="display:none;">✓ Presented</span>
      </div>
      <div class="tab-subtitle" id="count-Subtask-4">...</div>
    </button>
    <button class="tab-btn" onclick="switchSubtask('All')">
      <div class="tab-title"><span>Any Subtask</span></div>
      <div class="tab-subtitle" id="count-All">...</div>
    </button>
  </div>

  <!-- Main Stage & Controls -->
  <div class="main-grid">
    <div class="selector-card">
      <div class="status-banner" id="alreadyPresentedBanner">
        <span>⚠️ <span id="presentedBannerText">Already presented for this subtask</span></span>
      </div>

      <!-- Stage: Idle View -->
      <div class="selector-stage-empty" id="drawView">
        <div class="empty-icon">🎯</div>
        <div class="stage-title">Ready to Draw for <span id="stageSubtaskLabel" style="color:var(--primary);">Subtask 1</span></div>
        <div class="stage-desc">Drawing randomly from students who completed this subtask and have not presented.</div>
        <button class="btn-draw" id="drawBtn" onclick="requestDrawStudent()">
          🎲 Draw Student <span class="kbd-hint">Space</span>
        </button>
      </div>

      <!-- Stage: Selected Student View -->
      <div class="drawn-student-box" id="studentView" style="display: none;">
        <div class="drawn-tag">⭐️ Drawn for <span id="drawnTargetSubtask">Subtask 1</span> ⭐️</div>
        <div class="drawn-name" id="sName">Student Name</div>
        <div class="drawn-subline" id="sSubline">Attempted 4 subtasks</div>
        
        <div class="drawn-tasks" id="sTasks"></div>

        <div class="decision-grid">
          <button class="decision-btn btn-rule-pass" onclick="recordOutcome('pass')">
            <strong>✅ Passed Presentation <span class="kbd-hint">P</span></strong>
            <span>Satisfied requirements</span>
          </button>
          <button class="decision-btn btn-rule-fail" onclick="recordOutcome('fail')">
            <strong>⚠️ Failed Attempt <span class="kbd-hint">F</span></strong>
            <span>Cannot explain (no strike, stays in pool)</span>
          </button>
          <button class="decision-btn btn-rule-strike" onclick="recordOutcome('strike')">
            <strong>❌ Absent / Strike <span class="kbd-hint">S</span></strong>
            <span>Absent or refused (+1 strike)</span>
          </button>
          <button class="decision-btn btn-rule-excuse" onclick="recordOutcome('excuse')">
            <strong>🏥 Excused</strong>
            <span>Documented medical / official</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Side Panel Stats -->
    <div class="side-card">
      <div class="side-header">
        <span>Session Overview</span>
        <span style="font-size: 12px; color: var(--primary);" id="totalSubmissionsTag">0 Students</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">✨ Presented Successfully</span>
        <span class="stat-val" style="color: var(--success);" id="statPresented">0</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">⚠️ Strikes Recorded</span>
        <span class="stat-val" style="color: var(--danger);" id="statStrikes">0</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">🏥 Excused Absences</span>
        <span class="stat-val" id="statExcused">0</span>
      </div>
      <div class="stat-row">
        <span class="stat-label">👥 Remaining Pool</span>
        <span class="stat-val" style="color: var(--primary);" id="statRemaining">0</span>
      </div>

      <div class="rule-brief">
        <strong>Tutorial Rules:</strong><br>
        • Code does not need to be 100% perfect, but must be their own work.<br>
        • Valid submission requires attempting ≥ 2 subtasks.<br>
        • Cannot explain = Failed attempt, no strike.<br>
        • Absent without excuse = Strike. 2 strikes = disqualified.
      </div>
    </div>
  </div>

  <!-- Roster Section -->
  <div class="roster-card">
    <div class="roster-controls">
      <div>
        <div style="font-size: 16px; font-weight: 700;">Student Roster & Tasks</div>
        <div style="font-size: 12px; color: var(--text-dim); margin-top: 2px;">
          Click any badge (T1–T4) to toggle subtask status in real time. Pools update automatically.
        </div>
      </div>
      <input type="text" class="search-box" placeholder="Search student name..." id="searchInput" oninput="renderRoster()">
    </div>

    <!-- Filter Pills -->
    <div class="filter-pills-row">
      <span>Filter list:</span>
      <button class="filter-pill active" onclick="setRosterFilter('All', this)">All</button>
      <button class="filter-pill" onclick="setRosterFilter('Subtask 1', this)">Subtask 1</button>
      <button class="filter-pill" onclick="setRosterFilter('Subtask 2', this)">Subtask 2</button>
      <button class="filter-pill" onclick="setRosterFilter('Subtask 3', this)">Subtask 3</button>
      <button class="filter-pill" onclick="setRosterFilter('Subtask 4', this)">Subtask 4</button>
    </div>

    <table>
      <thead>
        <tr>
          <th>Student Name</th>
          <th>Subtasks Submitted (Click to Toggle)</th>
          <th>Strikes</th>
          <th>Session Status</th>
        </tr>
      </thead>
      <tbody id="rosterTbody"></tbody>
    </table>
  </div>
</div>

<script>
  let state = { students: [], history: [], session: 'default', available_sessions: [] };
  let currentSubtask = 'Subtask 1';
  let currentDrawnStudent = null;
  let currentRosterFilter = 'All';

  async function loadData() {
    const res = await fetch('/api/state');
    state = await res.json();
    
    // Update session selector dropdown
    const sel = document.getElementById('sessionSelect');
    sel.innerHTML = '';
    (state.available_sessions || []).forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.name;
      opt.innerText = s.name.replace('_', ' ');
      if (s.name === state.session) opt.selected = true;
      sel.appendChild(opt);
    });

    document.getElementById('sessionBadge').innerText = (state.session || 'Active').replace('_', ' ');
    render();
  }

  async function changeSession(sessionName) {
    const res = await fetch('/api/set_session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session: sessionName })
    });
    state = await res.json();
    currentDrawnStudent = null;
    document.getElementById('studentView').style.display = 'none';
    document.getElementById('drawView').style.display = 'block';
    document.getElementById('sessionBadge').innerText = (state.session || 'Active').replace('_', ' ');
    showToast("Switched to " + sessionName.replace('_', ' '));
    render();
  }

  function openIngestModal() {
    document.getElementById('ingestModal').style.display = 'flex';
  }

  function closeIngestModal() {
    document.getElementById('ingestModal').style.display = 'none';
  }

  async function runIngestFromModal() {
    const name = document.getElementById('ingestSessionName').value.trim();
    const lmsPath = document.getElementById('ingestLmsPath').value.trim();
    const basePath = document.getElementById('ingestBasePath').value.trim();
    const groupNum = document.getElementById('ingestGroupNum').value.trim();
    const rosterPath = document.getElementById('ingestRosterPath').value.trim();

    if (!lmsPath) {
      alert("Please provide the LMS Submissions file path (.xlsx or .csv)");
      return;
    }

    showToast("Ingesting submissions... please wait");
    const res = await fetch('/api/ingest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_name: name || 'exercise_session',
        lms_path: lmsPath,
        base_path: basePath || null,
        group: groupNum ? parseInt(groupNum) : null,
        roster_path: rosterPath || null
      })
    });

    if (res.ok) {
      state = await res.json();
      closeIngestModal();
      showToast("Ingest complete! Session loaded 🎉");
      loadData();
    } else {
      const err = await res.json();
      alert("Ingest error: " + (err.error || "Failed to process files"));
    }
  }

  function getPresenters(subtask) {
    if (subtask === 'All') return [];
    return state.students.filter(s => s.has_presented && s.subtask_presented === subtask);
  }

  function getEligible(subtask) {
    return state.students.filter(s => {
      if (s.has_presented) return false;
      if (s.status === 'disqualified' || s.status === 'excused') return false;
      if ((s.subtasks_attempted || []).length < 2) return false;
      if (subtask === 'All') return true;
      return s.subtasks_attempted && s.subtasks_attempted.includes(subtask);
    });
  }

  function switchSubtask(subtask) {
    currentSubtask = subtask;
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.innerText.includes(subtask === 'All' ? 'Any' : subtask));
    });
    currentDrawnStudent = null;
    document.getElementById('studentView').style.display = 'none';
    document.getElementById('drawView').style.display = 'block';
    render();
  }

  function setRosterFilter(filter, btn) {
    currentRosterFilter = filter;
    document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderRoster();
  }

  function requestDrawStudent() {
    const presenters = getPresenters(currentSubtask);
    if (presenters.length > 0 && currentSubtask !== 'All') {
      const names = presenters.map(p => p.full_name).join(', ');
      document.getElementById('modalTitle').innerText = `${currentSubtask} Already Presented`;
      document.getElementById('modalBody').innerHTML = `
        <strong>${names}</strong> has already presented <strong>${currentSubtask}</strong>.<br><br>
        Are you sure you want to select another student for this subtask anyway?
      `;
      document.getElementById('subtaskWarningModal').style.display = 'flex';
      return;
    }
    drawStudent();
  }

  function closeWarningModal() {
    document.getElementById('subtaskWarningModal').style.display = 'none';
  }

  function confirmDrawAgain() {
    closeWarningModal();
    drawStudent();
  }

  function drawStudent() {
    const eligible = getEligible(currentSubtask);
    if (eligible.length === 0) {
      alert("No eligible students remaining for " + currentSubtask + "!");
      return;
    }

    const drawBtn = document.getElementById('drawBtn');
    drawBtn.disabled = true;

    let counter = 0;
    const interval = setInterval(() => {
      const rand = eligible[Math.floor(Math.random() * eligible.length)];
      drawBtn.innerText = "🎲 " + rand.full_name;
      counter++;
      if (counter > 12) {
        clearInterval(interval);
        currentDrawnStudent = eligible[Math.floor(Math.random() * eligible.length)];
        showDrawnStudent(currentDrawnStudent);
        drawBtn.disabled = false;
        drawBtn.innerHTML = '🎲 Draw Student <span class="kbd-hint">Space</span>';
      }
    }, 70);
  }

  function showDrawnStudent(s) {
    document.getElementById('drawView').style.display = 'none';
    const sView = document.getElementById('studentView');
    sView.style.display = 'block';

    document.getElementById('sName').innerText = s.full_name;
    document.getElementById('drawnTargetSubtask').innerText = currentSubtask;
    document.getElementById('sSubline').innerText = `Attempted ${s.attempt_count} subtasks`;

    const tasksContainer = document.getElementById('sTasks');
    tasksContainer.innerHTML = '';
    
    ['Subtask 1', 'Subtask 2', 'Subtask 3', 'Subtask 4'].forEach(t => {
      const isDone = (s.subtasks_attempted || []).includes(t);
      const isCurrent = (t === currentSubtask);
      const btn = document.createElement('button');
      btn.className = 'task-pill ' + (isDone ? (isCurrent ? 'active-pill' : 'done-pill') : 'missing-pill');
      btn.title = isDone ? `Click to remove ${t}` : `Click to add ${t}`;
      btn.innerHTML = `<span>${isDone ? '✓' : '+'}</span> ${t}` + (isCurrent ? ' <span style="font-size:10px; opacity:0.8;">(Target)</span>' : '');
      btn.onclick = () => toggleSubtask(s.id, t);
      tasksContainer.appendChild(btn);
    });
  }

  async function toggleSubtask(studentId, subtask, ev) {
    if (ev) ev.stopPropagation();
    const res = await fetch('/api/toggle_subtask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ student_id: studentId, subtask: subtask })
    });
    if (res.ok) {
      state = await res.json();
      const student = state.students.find(s => s.id === studentId);
      const hasTask = student && student.subtasks_attempted && student.subtasks_attempted.includes(subtask);
      const shortTask = subtask.replace('Subtask ', 'T');
      showToast(`${hasTask ? 'Added' : 'Removed'} ${shortTask} for ${student ? student.full_name : studentId}`);
      
      if (currentDrawnStudent && currentDrawnStudent.id === studentId) {
        currentDrawnStudent = student;
        showDrawnStudent(student);
      }
      render();
    }
  }

  async function recordOutcome(outcome) {
    if (!currentDrawnStudent) return;
    const name = currentDrawnStudent.full_name;
    const res = await fetch('/api/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        student_id: currentDrawnStudent.id,
        outcome: outcome,
        subtask: currentSubtask
      })
    });
    state = await res.json();
    currentDrawnStudent = null;
    document.getElementById('studentView').style.display = 'none';
    document.getElementById('drawView').style.display = 'block';

    if (outcome === 'pass') {
      showToast(`${name} passed presentation! 🎉`);
      triggerConfetti();
    } else if (outcome === 'strike') {
      showToast(`Strike recorded for ${name} ⚠️`);
    } else if (outcome === 'fail') {
      showToast(`Failed attempt logged (stays in pool)`);
    } else {
      showToast(`${name} marked as excused`);
    }

    render();
  }

  async function resetSession() {
    if (!confirm("Are you sure you want to reset presentations and strikes for this session?")) return;
    const res = await fetch('/api/reset', { method: 'POST' });
    state = await res.json();
    currentDrawnStudent = null;
    document.getElementById('studentView').style.display = 'none';
    document.getElementById('drawView').style.display = 'block';
    showToast("Session reset");
    render();
  }

  function exportReport() {
    window.open('/api/export', '_blank');
  }

  function showToast(msg) {
    const t = document.getElementById('toast');
    t.innerText = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2600);
  }

  function renderSubtaskBadges(s) {
    const tasks = s.subtasks_attempted || [];
    const count = tasks.length;
    const isRule3Valid = count >= 2;
    
    let html = '';
    ['Subtask 1', 'Subtask 2', 'Subtask 3', 'Subtask 4'].forEach((t, i) => {
      const isDone = tasks.includes(t);
      const shortName = 'T' + (i + 1);
      html += `
        <button class="task-badge-btn ${isDone ? 'active' : 'inactive'}"
          onclick="toggleSubtask('${s.id}', '${t}', event)"
          title="${t}: ${isDone ? 'Submitted (click to remove)' : 'Not submitted (click to add)'}">
          <span>${isDone ? '✓' : '✗'}</span> ${shortName}
        </button>
      `;
    });
    
    html += `
      <span class="badge-total-count" style="${isRule3Valid ? '' : 'color:#f87171;'}">
        ${count}/4 ${isRule3Valid ? '' : '⚠️'}
      </span>
    `;
    return html;
  }

  function render() {
    ['Subtask 1', 'Subtask 2', 'Subtask 3', 'Subtask 4', 'All'].forEach(t => {
      const el = document.getElementById('count-' + t.replace(' ', '-'));
      if (el) el.innerText = getEligible(t).length + ' eligible';
      
      const presTag = document.getElementById('pres-' + t.replace(' ', '-'));
      if (presTag) {
        const presenters = getPresenters(t);
        if (presenters.length > 0) {
          presTag.style.display = 'inline-block';
          presTag.innerText = `✓ ${presenters[0].full_name.split(' ')[0]}`;
        } else {
          presTag.style.display = 'none';
        }
      }
    });

    const banner = document.getElementById('alreadyPresentedBanner');
    const bannerText = document.getElementById('presentedBannerText');
    const currentPresenters = getPresenters(currentSubtask);
    if (currentPresenters.length > 0 && currentSubtask !== 'All') {
      bannerText.innerText = `${currentSubtask} presented by ${currentPresenters.map(p => p.full_name).join(', ')}`;
      banner.style.display = 'block';
    } else {
      banner.style.display = 'none';
    }

    document.getElementById('stageSubtaskLabel').innerText = currentSubtask === 'All' ? 'Any Subtask' : currentSubtask;

    const students = state.students;
    document.getElementById('totalSubmissionsTag').innerText = students.length + ' Students';
    document.getElementById('statPresented').innerText = students.filter(s => s.has_presented).length;
    document.getElementById('statStrikes').innerText = students.filter(s => s.strikes > 0).reduce((acc, s) => acc + s.strikes, 0);
    document.getElementById('statExcused').innerText = students.filter(s => s.status === 'excused').length;
    document.getElementById('statRemaining').innerText = getEligible(currentSubtask).length;

    renderRoster();
  }

  function renderRoster() {
    const query = (document.getElementById('searchInput').value || '').toLowerCase();
    let filtered = state.students.filter(s => s.full_name.toLowerCase().includes(query));

    if (currentRosterFilter !== 'All') {
      filtered = filtered.filter(s => (s.subtasks_attempted || []).includes(currentRosterFilter));
    }

    const tbody = document.getElementById('rosterTbody');
    tbody.innerHTML = '';
    filtered.forEach(s => {
      const tr = document.createElement('tr');
      let statusBadge = '<span class="badge-status status-tag-eligible">Eligible</span>';
      if (s.has_presented) {
        statusBadge = `<span class="badge-status status-tag-presented">Presented (${s.subtask_presented || 'Done'})</span>`;
      } else if (s.strikes >= 2) {
        statusBadge = '<span class="badge-status status-tag-strike">2 Strikes (Disqualified)</span>';
      } else if (s.strikes === 1) {
        statusBadge = '<span class="badge-status status-tag-strike">1 Strike</span>';
      } else if (s.status === 'excused') {
        statusBadge = '<span class="badge-status status-tag-excused">Excused</span>';
      } else if ((s.subtasks_attempted || []).length < 2) {
        statusBadge = '<span class="badge-status" style="background:#3b1414; color:#f87171;">&lt;2 Tasks</span>';
      }

      let strikeVisual = '<span style="color:#64748b;">⚪ ⚪</span>';
      if (s.strikes === 1) strikeVisual = '<span>🔴 ⚪</span>';
      if (s.strikes >= 2) strikeVisual = '<span>🔴 🔴</span>';

      tr.innerHTML = `
        <td><strong style="font-size:14px;">${s.full_name}</strong></td>
        <td><div class="subtask-badges-wrap">${renderSubtaskBadges(s)}</div></td>
        <td>${strikeVisual}</td>
        <td>${statusBadge}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  window.addEventListener('keydown', (e) => {
    if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
    const warnModal = document.getElementById('subtaskWarningModal');
    const ingModal = document.getElementById('ingestModal');
    if (warnModal.style.display === 'flex' || ingModal.style.display === 'flex') {
      if (e.key === 'Escape') {
        closeWarningModal();
        closeIngestModal();
      }
      return;
    }

    if (e.code === 'Space') {
      e.preventDefault();
      if (!currentDrawnStudent) requestDrawStudent();
    } else if (e.key === 'p' || e.key === 'P') {
      if (currentDrawnStudent) recordOutcome('pass');
    } else if (e.key === 'f' || e.key === 'F') {
      if (currentDrawnStudent) recordOutcome('fail');
    } else if (e.key === 's' || e.key === 'S') {
      if (currentDrawnStudent) recordOutcome('strike');
    } else if (e.key === 'Escape') {
      if (currentDrawnStudent) {
        currentDrawnStudent = null;
        document.getElementById('studentView').style.display = 'none';
        document.getElementById('drawView').style.display = 'block';
      }
    }
  });

  function triggerConfetti() {
    const canvas = document.getElementById('confettiCanvas');
    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const pieces = [];
    const colors = ['#38bdf8', '#34d399', '#f59e0b', '#ec4899', '#a855f7'];

    for (let i = 0; i < 80; i++) {
      pieces.push({
        x: canvas.width / 2,
        y: canvas.height / 2,
        w: Math.random() * 8 + 4,
        h: Math.random() * 8 + 4,
        vx: (Math.random() - 0.5) * 16,
        vy: (Math.random() - 0.8) * 16,
        color: colors[Math.floor(Math.random() * colors.length)],
        tilt: Math.random() * 10,
        tiltAngle: 0,
        tiltAngleInc: (Math.random() * 0.07) + 0.05
      });
    }

    let frame = 0;
    function animate() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      pieces.forEach(p => {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.35;
        p.tiltAngle += p.tiltAngleInc;
        p.tilt = Math.sin(p.tiltAngle) * 12;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.fillRect(p.x, p.y, p.w, p.h);
      });
      frame++;
      if (frame < 120) requestAnimationFrame(animate);
      else ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    animate();
  }

  loadData();
</script>
</body>
</html>
"""


class AppServer:
    def __init__(
        self,
        session_manager_or_path: Union[SessionManager, Path, str],
        session_dir: Optional[Union[Path, str]] = None,
        port: int = 8006,
    ):
        if isinstance(session_manager_or_path, SessionManager):
            self.session_manager = session_manager_or_path
            self.port = port
        else:
            data_path = Path(session_manager_or_path).resolve()
            sm = SessionManager(base_dir=data_path.parent, default_session_path=data_path)
            if session_dir:
                sm.active_session_dir = Path(session_dir).resolve()
                sm.active_session_dir.mkdir(parents=True, exist_ok=True)
            self.session_manager = sm
            self.port = port

    def get_state(self) -> Dict[str, Any]:
        students = self.session_manager.get_current_students()
        session_state = load_session_state(self.session_manager.active_session_dir) if self.session_manager.active_session_dir else {}
        return {
            "session": self.session_manager.active_session_name,
            "available_sessions": self.session_manager.list_sessions(),
            "students": students,
            "history": session_state.get("history", []),
        }

    def run(self, auto_open: bool = True):
        server_instance = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                url = urllib.parse.urlparse(self.path)
                if url.path in ("/", "/index.html"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(HTML_PAGE.encode("utf-8"))
                elif url.path == "/api/state":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(server_instance.get_state(), ensure_ascii=False).encode("utf-8"))
                elif url.path == "/api/export":
                    state = server_instance.get_state()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", f'attachment; filename="{state["session"]}_report.csv"')
                    self.end_headers()
                    output = "Full Name,Attempted Subtasks,Presented,Subtask Presented,Strikes,Status\n"
                    for s in state["students"]:
                        output += f'"{s["full_name"]}","{"; ".join(s.get("subtasks_attempted",[]))}","{"Yes" if s.get("has_presented") else "No"}","{s.get("subtask_presented","")}","{s.get("strikes",0)}","{s.get("status","eligible")}"\n'
                    self.wfile.write(output.encode("utf-8-sig"))
                else:
                    self.send_error(404)

            def do_POST(self):
                url = urllib.parse.urlparse(self.path)
                length = int(self.headers.get("Content-Length", 0))
                post_data = self.rfile.read(length) if length > 0 else b"{}"
                payload = json.loads(post_data.decode("utf-8")) if post_data else {}

                state = server_instance.get_state()
                students = state["students"]
                history = state.get("history", [])

                if url.path == "/api/set_session":
                    session_name = payload.get("session")
                    if session_name:
                        server_instance.session_manager.set_active_session(session_name)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(server_instance.get_state(), ensure_ascii=False).encode("utf-8"))

                elif url.path == "/api/ingest":
                    session_name = payload.get("session_name", "session")
                    lms_path = Path(payload.get("lms_path", "")).resolve()
                    base_path = Path(payload.get("base_path")).resolve() if payload.get("base_path") else None
                    group = payload.get("group")
                    roster_path = Path(payload.get("roster_path")).resolve() if payload.get("roster_path") else None

                    if not lms_path.exists():
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": f"LMS file not found: {lms_path}"}).encode("utf-8"))
                        return

                    session_dir = server_instance.session_manager.sessions_dir / session_name
                    process_submissions_folder(
                        submissions_file=lms_path,
                        base_notebook=base_path,
                        group_filter=group,
                        output_dir=session_dir,
                        roster_csv=roster_path,
                    )
                    server_instance.session_manager.set_active_session(session_name)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(server_instance.get_state(), ensure_ascii=False).encode("utf-8"))

                elif url.path == "/api/action":
                    sid = payload.get("student_id")
                    outcome = payload.get("outcome")
                    subtask = payload.get("subtask")

                    for s in students:
                        if s["id"] == sid:
                            if outcome == "pass":
                                s["has_presented"] = True
                                s["subtask_presented"] = subtask
                                s["status"] = "presented"
                                history.append({"student": s["full_name"], "action": "passed", "subtask": subtask})
                            elif outcome == "fail":
                                history.append({"student": s["full_name"], "action": "failed_attempt", "subtask": subtask})
                            elif outcome == "strike":
                                s["strikes"] = s.get("strikes", 0) + 1
                                if s["strikes"] >= 2:
                                    s["status"] = "disqualified"
                                history.append({"student": s["full_name"], "action": "strike", "strikes": s["strikes"], "subtask": subtask})
                            elif outcome == "excuse":
                                s["status"] = "excused"
                                history.append({"student": s["full_name"], "action": "excused", "subtask": subtask})
                            break

                    server_instance.session_manager.save_state(students, history)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(server_instance.get_state(), ensure_ascii=False).encode("utf-8"))

                elif url.path == "/api/toggle_subtask":
                    sid = payload.get("student_id")
                    subtask = payload.get("subtask")

                    for s in students:
                        if s["id"] == sid:
                            tasks = list(s.get("subtasks_attempted", []))
                            if subtask in tasks:
                                tasks.remove(subtask)
                            else:
                                tasks.append(subtask)

                            def sort_key(t):
                                m = re.search(r"\d+", t)
                                return int(m.group(0)) if m else t
                            tasks.sort(key=sort_key)
                            
                            s["subtasks_attempted"] = tasks
                            s["attempt_count"] = len(tasks)
                            s["valid_submission"] = len(tasks) >= 2
                            break

                    server_instance.session_manager.save_state(students, history)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(server_instance.get_state(), ensure_ascii=False).encode("utf-8"))

                elif url.path == "/api/reset":
                    if server_instance.session_manager.active_session_dir:
                        state_file = server_instance.session_manager.active_session_dir / "session_state.json"
                        if state_file.exists():
                            os.remove(state_file)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(server_instance.get_state(), ensure_ascii=False).encode("utf-8"))

                else:
                    self.send_error(404)

        server = HTTPServer(("127.0.0.1", self.port), Handler)
        url = f"http://localhost:{self.port}"
        print(f"\n🚀 Student Picker running at: {url}")
        print("📂 Active Session: " + self.session_manager.active_session_name)
        print("🔒 Projection Safe: Student emails and private records hidden")
        print("Press Ctrl+C to stop.\n")

        if auto_open:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            server.server_close()
