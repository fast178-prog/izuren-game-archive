let allVideos = [];
let siteConfig = {};

const BUILD_VERSION = "multi-genre-v2";

const table = document.getElementById("videoTable");
const searchInput = document.getElementById("searchInput");
const sortSelect = document.getElementById("sortSelect");
const totalCount = document.getElementById("totalCount");
const genreFilter = document.getElementById("genreFilter");
const clearGenreButton = document.getElementById("clearGenreButton");

function jsonUrl(fileName) {
  return `${fileName}?v=${Date.now()}`;
}

async function loadConfig() {
  try {
    const response = await fetch(jsonUrl("site-config.json"), { cache: "no-store" });
    if (!response.ok) throw new Error("site-config.json을 불러오지 못했습니다.");
    siteConfig = await response.json();
  } catch (error) {
    console.error(error);
    alert("site-config.json을 읽지 못했습니다. start_server.bat으로 실행하세요.");
    siteConfig = {};
  }

  applyConfig();
}

function applyConfig() {
  setText("browserTitle", siteConfig.title);
  setText("siteEyebrow", siteConfig.eyebrow);
  setText("siteTitle", siteConfig.title);
  setText("siteDescription", siteConfig.description);
  setText("genreFilterTitle", siteConfig.genreFilterTitle);
  setText("clearGenreButton", siteConfig.clearGenreButtonText);

  if (siteConfig.searchPlaceholder) {
    searchInput.placeholder = siteConfig.searchPlaceholder;
  }

  const headers = siteConfig.tableHeaders || {};
  setText("thGameTitle", headers.gameTitle);
  setText("thDate", headers.date);
  setText("thGenre", headers.genre);
  setText("thMemo", headers.memo);
  setText("thLink", headers.link);
}

function setText(id, value) {
  if (value === undefined || value === null) return;
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

async function loadVideos() {
  try {
    const response = await fetch(jsonUrl("videos.json"), { cache: "no-store" });
    if (!response.ok) throw new Error("videos.json을 불러오지 못했습니다.");
    const rawVideos = await response.json();

    if (!Array.isArray(rawVideos)) {
      throw new Error("videos.json의 최상위 구조는 배열 [] 이어야 합니다.");
    }

    allVideos = rawVideos.map(normalizeVideo).filter(video => video.gameTitle || video.url);
  } catch (error) {
    console.error(error);
    alert("videos.json을 읽지 못했습니다. JSON 문법 또는 실행 방식을 확인하세요.");
    allVideos = [];
  }

  setupGenreFilters();
  renderVideos();
}

function normalizeVideo(video) {
  const genreValue = video.genre ?? video.category ?? "";

  return {
    gameTitle: video.gameTitle ?? video.title ?? video.videoTitle ?? "",
    date: video.date ?? video.publishedAt ?? video.publishedDate ?? "",
    genre: Array.isArray(genreValue) ? genreValue.join(",") : String(genreValue),
    genres: splitGenres(genreValue),
    memo: video.memo ?? video.note ?? "",
    url: video.url ?? video.link ?? video.videoUrl ?? ""
  };
}

function splitGenres(value) {
  if (Array.isArray(value)) {
    return value.flatMap(item => splitGenres(item));
  }

  return String(value)
    // 지원 구분자: 영어 쉼표, 한글/중국어 쉼표, 슬래시, 세로줄
    .split(/[,，、/|]+/)
    .map(v => v.trim())
    .filter(Boolean);
}

function setupGenreFilters() {
  const existingGenres = [...new Set(allVideos.flatMap(video => video.genres || []))];

  let genres = Array.isArray(siteConfig.genreFilterOrder) && siteConfig.genreFilterOrder.length > 0
    ? siteConfig.genreFilterOrder.flatMap(item => splitGenres(item)).filter(genre => existingGenres.includes(genre))
    : [];

  const remainingGenres = existingGenres
    .filter(genre => !genres.includes(genre))
    .sort((a, b) => a.localeCompare(b, "ko"));

  genres = [...new Set([...genres, ...remainingGenres])];

  genreFilter.innerHTML = genres.map(genre => `
    <label class="genre-check">
      <input type="checkbox" value="${escapeAttr(genre)}" />
      <span>${escapeHtml(getGenreDisplayName(genre))}</span>
    </label>
  `).join("");

  genreFilter.querySelectorAll("input[type='checkbox']").forEach(checkbox => {
    checkbox.addEventListener("change", renderVideos);
  });
}

function getSelectedGenres() {
  return [...genreFilter.querySelectorAll("input[type='checkbox']:checked")]
    .map(input => input.value);
}

function renderVideos() {
  const keyword = searchInput.value.trim().toLowerCase();
  const sortMode = sortSelect.value;
  const selectedGenres = getSelectedGenres();

  let list = allVideos.filter(video => {
    const target = `${video.gameTitle} ${video.genre ?? ""} ${video.memo ?? ""}`.toLowerCase();
    const keywordMatched = target.includes(keyword);
    const genreMatched =
      selectedGenres.length === 0 ||
      selectedGenres.every(selectedGenre => (video.genres || []).includes(selectedGenre));

    return keywordMatched && genreMatched;
  });

  list.sort((a, b) => {
    if (sortMode === "newest") return new Date(b.date || "1900-01-01") - new Date(a.date || "1900-01-01");
    if (sortMode === "oldest") return new Date(a.date || "1900-01-01") - new Date(b.date || "1900-01-01");
    return String(a.gameTitle).localeCompare(String(b.gameTitle), "ko");
  });

  totalCount.textContent = list.length;

  table.innerHTML = list.map(video => `
    <tr>
      <td>${escapeHtml(video.gameTitle)}</td>
      <td>${escapeHtml(video.date)}</td>
      <td>${renderGenreBadges(video.genres)}</td>
      <td>${escapeHtml(video.memo || "")}</td>
      <td><a class="watch" href="${escapeAttr(video.url)}" target="_blank" rel="noopener noreferrer">보러가기</a></td>
    </tr>
  `).join("");
}

function renderGenreBadges(genres) {
  if (!genres || genres.length === 0) {
    return `<span class="genre">-</span>`;
  }

  return genres.map(genre => `<span class="genre">${escapeHtml(genre)}</span>`).join(" ");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

searchInput.addEventListener("input", renderVideos);
sortSelect.addEventListener("change", renderVideos);

clearGenreButton.addEventListener("click", () => {
  genreFilter.querySelectorAll("input[type='checkbox']").forEach(checkbox => {
    checkbox.checked = false;
  });
  renderVideos();
});

async function init() {
  console.log("site build:", BUILD_VERSION);
  await loadConfig();
  await loadVideos();
}
function getGenreDisplayName(genre) {
  const displayNames = siteConfig.genreDisplayNames || {};
  return displayNames[genre] || genre;
}

init();
