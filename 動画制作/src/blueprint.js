// 分析結果（編集構造）から、オリジナル動画の設計図を作る。API は使わない。
// 設計図に入れるのは「章の役割・尺の配分・シーンの種類の並び・テンポ」だけで、参照動画の内容は入れない。

// pipeline/planner.py の SCENE_TYPES と同じ（テストで一致を確かめている）
export const SCENE_KINDS = ['statement', 'big_number', 'year', 'map', 'dot_grid', 'compare'];

// 分析の visual_type → 描画できるシーンの種類。note があるものは、そのままでは再現できない
export const VISUAL_TO_KIND = {
  map: { kind: 'map' },
  wide_map: { kind: 'map' },
  historic_map: { kind: 'map', note: 'セピア地図は color.sepia_ocean / color.sepia_land が未計測のため使えない。通常の地図で代用' },
  big_number: { kind: 'big_number' },
  year: { kind: 'year' },
  dot_grid: { kind: 'dot_grid' },
  chart: { kind: 'compare' },
  title_card: { kind: 'statement' },
  statement: { kind: 'statement' },
  other: { kind: 'statement' },
  photo: { kind: 'statement', note: '写真シーンは未対応（権利確認が必要）。statement で代用' },
  footage: { kind: 'statement', note: '実写映像は未対応。statement で代用' },
  timeline: { kind: 'statement', note: 'タイムラインは未対応。statement で代用' },
  diagram: { kind: 'statement', note: '図解は未対応。statement で代用' },
};

const round = (value, digits = 2) => Math.round(value * 10 ** digits) / 10 ** digits;

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function countBy(items, key) {
  const counts = {};
  for (const item of items) counts[item[key]] = (counts[item[key]] ?? 0) + 1;
  return counts;
}

// targetSec を渡すと、章とシーンの尺を元の比率のまま目標の長さに伸縮する
export function buildBlueprint(record, { targetSec = null } = {}) {
  const { analysis, meta } = record;
  const sourceSec = analysis.video.duration_sec;
  const totalSec = targetSec ?? sourceSec;
  const scale = totalSec / sourceSec;
  const sceneSecs = analysis.scenes.map((s) => s.end_sec - s.start_sec);

  const notes = new Map();
  const sequence = analysis.scenes.map((scene) => {
    const mapping = VISUAL_TO_KIND[scene.visual_type];
    if (mapping.note) notes.set(scene.visual_type, { visual_type: scene.visual_type, note: mapping.note, count: (notes.get(scene.visual_type)?.count ?? 0) + 1 });
    return {
      chapter_index: scene.chapter_index,
      start_sec: round(scene.start_sec * scale, 1),
      duration_sec: round((scene.end_sec - scene.start_sec) * scale, 1),
      kind: mapping.kind,
      source_visual_type: scene.visual_type,
      camera: scene.camera,
      transition_in: scene.transition_in,
      overlays: scene.overlays,
      elements_added: scene.elements_added,
      narration_role: scene.narration_role,
      direction: scene.description,
    };
  });

  const chapters = analysis.chapters.map((chapter) => {
    const scenes = sequence.filter((s) => s.chapter_index === chapter.index);
    return {
      index: chapter.index,
      role: chapter.role,
      purpose: chapter.purpose,
      ratio: round((chapter.end_sec - chapter.start_sec) / sourceSec, 3),
      duration_sec: round((chapter.end_sec - chapter.start_sec) * scale, 1),
      scene_count: scenes.length,
      kinds: countBy(scenes, 'kind'),
    };
  });

  return {
    source: {
      url: meta.url,
      model: meta.model,
      analyzed_at: meta.analyzed_at,
      duration_sec: sourceSec,
    },
    total_sec: round(totalSec, 1),
    style: analysis.overall,
    pacing: {
      scene_count: sequence.length,
      median_scene_sec: round(median(sceneSecs) * scale, 1),
      scenes_per_minute: round(sequence.length / (totalSec / 60), 1),
      kinds: countBy(sequence, 'kind'),
      transitions: countBy(sequence, 'transition_in'),
    },
    techniques: analysis.techniques,
    chapters,
    sequence,
    unsupported: [...notes.values()],
    uncertain: analysis.uncertain,
  };
}
