// 视觉回归专用固定数据：仅当页面收到 visualState 查询参数时启用，避免截图依赖真实登录、时间或 AI 接口。
const MOCK_UPLOAD_IMAGE = '/assets/visual-mock/upload-sample-design.png';

const AMALFI_ITEMS = [
  {
    pattern_id: '14-57204-001',
    code: '14-57204-001',
    decor_name: 'Amalfi',
    category: 'abstract',
    image_url: '/assets/visual-mock/amalfi-001.png',
    confidence: 0.96,
    favorited: true
  },
  {
    pattern_id: '14-24123-002',
    code: '14-24123-002',
    decor_name: 'Amalfi',
    category: 'abstract',
    image_url: '/assets/visual-mock/amalfi-002.png',
    confidence: 0.93,
    favorited: true
  },
  {
    pattern_id: '14-57204-003',
    code: '14-57204-003',
    decor_name: 'Amalfi',
    category: 'abstract',
    image_url: '/assets/visual-mock/amalfi-003.png',
    confidence: 0.9,
    favorited: true
  },
  {
    pattern_id: '14-57204-004',
    code: '14-57204-004',
    decor_name: 'Amalfi',
    category: 'abstract',
    image_url: '/assets/visual-mock/amalfi-004.png',
    confidence: 0.87,
    favorited: true
  },
  {
    pattern_id: '14-57204-005',
    code: '14-57204-005',
    decor_name: 'Amalfi',
    category: 'abstract',
    image_url: '/assets/visual-mock/amalfi-002.png',
    confidence: 0.84,
    favorited: false
  },
  {
    pattern_id: '14-57204-006',
    code: '14-57204-006',
    decor_name: 'Amalfi',
    category: 'abstract',
    image_url: '/assets/visual-mock/amalfi-003.png',
    confidence: 0.81,
    favorited: true
  }
];

const WOOD_ITEMS = [
  {
    pattern_id: '14-18392-100',
    code: '14-18392-100',
    decor_name: 'Modena Oak',
    category: 'wood',
    image_url: '/assets/visual-mock/modena-oak-clean.jpg',
    confidence: 0.96,
    favorited: false
  },
  {
    pattern_id: '14-24123-003',
    code: '14-24123-003',
    decor_name: 'Castillo Teak',
    category: 'wood',
    image_url: '/assets/visual-mock/terra-oak-clean.jpg',
    confidence: 0.93,
    favorited: true
  },
  {
    pattern_id: '14-57204-002',
    code: '14-57204-002',
    decor_name: 'Amalfi',
    category: 'abstract',
    image_url: '/assets/visual-mock/amalfi-002-clean.jpg',
    confidence: 0.9,
    favorited: true
  },
  {
    pattern_id: '14-18129-002',
    code: '14-18129-002',
    decor_name: 'Terra Oak',
    category: 'wood',
    image_url: '/assets/visual-mock/modena-oak-clean.jpg',
    confidence: 0.87,
    favorited: false
  },
  {
    pattern_id: '14-18092-001',
    code: '14-18092-001',
    decor_name: 'Jolie',
    category: 'plain',
    image_url: '/assets/visual-mock/jolie.jpg',
    confidence: 0.84,
    favorited: false
  },
  {
    pattern_id: '14-18101-004',
    code: '14-18101-004',
    decor_name: 'Bluestone',
    category: 'stone',
    image_url: '/assets/visual-mock/stone.jpg',
    confidence: 0.81,
    favorited: true
  }
];

const MIXED_ITEMS = [
  WOOD_ITEMS[0],
  WOOD_ITEMS[1],
  AMALFI_ITEMS[1],
  WOOD_ITEMS[3],
  WOOD_ITEMS[4],
  WOOD_ITEMS[5]
];

const MOCK_ITEMS = AMALFI_ITEMS;

const STATE_ALIASES = {
  'results-grid': 'home-results-grid',
  'results-single': 'home-results-single',
  'upload-ready': 'home-upload-ready',
  'unmatched-modal': 'home-unmatched-modal',
  'upload-results': 'home-upload-results',
  'results-with-upload': 'home-results-with-upload',
  'detail-zoom': 'home-detail-zoom',
  'results-six': 'home-results-six',
  'feedback-negative': 'home-feedback-negative',
  'feedback-positive': 'home-feedback-positive',
  favorites: 'mine-favorites',
  history: 'mine-history'
};

function normalizeStateId(stateId) {
  return STATE_ALIASES[stateId] || stateId || '';
}

function takeItems(count, source) {
  return (source || MOCK_ITEMS).slice(0, count);
}

function baseVisualState(stateId) {
  return {
    visualMockActive: true,
    visualState: stateId,
    loading: false,
    message: '',
    feedbackLoading: false,
    leadLoading: false,
    unmatchedDialogVisible: false,
    feedbackRating: 0,
    feedbackDontRemind: false,
    visualSyntheticTabbar: false,
    searchBoxVisible: true,
    imagePanelMode: 'full',
    controlsVisible: true
  };
}

function format(formatItems, items) {
  return formatItems(items || []);
}

function resultState(stateId, options, count, extra, sourceItems) {
  const rawItems = takeItems(count, sourceItems);
  const results = format(options.formatItems, rawItems);
  return Object.assign(baseVisualState(stateId), {
    query: '',
    category: '',
    matchMode: options.config.MATCH_MODES.auto,
    imagePath: '',
    results,
    resultCount: results.length,
    recognitionId: 'visual-recognition-001',
    recognition_id: 'visual-recognition-001',
    threshold: 0.75,
    allTopResults: rawItems,
    all_top_results: rawItems,
    feedbackVisible: false,
    feedbackSubmitted: false,
    feedbackDialogVisible: false,
    feedbackCorrectPatternId: '',
    feedbackNote: '',
    detailVisible: false,
    selectedIndex: 0,
    selectedItem: null,
    detailCountText: options.config.UI_TEXT.emptyDetailCount,
    searchBoxVisible: true,
    imagePanelMode: 'none',
    controlsVisible: false,
    serviceVisible: true
  }, extra || {});
}

function homeState(stateId, options) {
  const text = options.text;
  const config = options.config;

  switch (stateId) {
    case 'home-default':
      return Object.assign(baseVisualState(stateId), {
        query: '',
        category: config.CATEGORY_VALUES.stone,
        matchMode: config.MATCH_MODES.auto,
        imagePath: '',
        results: [],
        resultCount: 0,
        recognitionId: '',
        recognition_id: '',
        threshold: 0,
        allTopResults: [],
        all_top_results: [],
        feedbackVisible: false,
        feedbackSubmitted: false,
        feedbackDialogVisible: false,
        unmatchedDialogVisible: false,
        feedbackCorrectPatternId: '',
        feedbackNote: '',
        detailVisible: false,
        selectedItem: null,
        detailCountText: config.UI_TEXT.emptyDetailCount,
        searchBoxVisible: true,
        imagePanelMode: 'full',
        controlsVisible: true,
        serviceVisible: true
      });
    case 'home-results-grid':
      return resultState(stateId, options, 5, { query: '57204' });
    case 'home-results-single':
      return resultState(stateId, options, 1, { query: '14-57204-001' });
    case 'home-upload-ready':
      return resultState(stateId, options, 0, {
        imagePath: MOCK_UPLOAD_IMAGE,
        category: config.CATEGORY_VALUES.wood,
        matchMode: config.MATCH_MODES.auto,
        searchBoxVisible: true,
        imagePanelMode: 'full',
        controlsVisible: true
      });
    case 'home-unmatched-modal':
      return resultState(stateId, options, 0, {
        imagePath: MOCK_UPLOAD_IMAGE,
        category: config.CATEGORY_VALUES.wood,
        message: '',
        feedbackVisible: false,
        unmatchedDialogVisible: true,
        recognitionId: 'visual-unmatched-001',
        recognition_id: 'visual-unmatched-001',
        searchBoxVisible: true,
        imagePanelMode: 'full',
        controlsVisible: true
      });
    case 'home-upload-results':
      return resultState(stateId, options, 2, {
        imagePath: MOCK_UPLOAD_IMAGE,
        category: config.CATEGORY_VALUES.wood,
        resultCount: 10,
        searchBoxVisible: false,
        imagePanelMode: 'full',
        controlsVisible: true
      }, WOOD_ITEMS);
    case 'home-results-with-upload':
      return resultState(stateId, options, 4, {
        imagePath: MOCK_UPLOAD_IMAGE,
        category: config.CATEGORY_VALUES.wood,
        resultCount: 10,
        searchBoxVisible: false,
        imagePanelMode: 'compact',
        controlsVisible: false
      }, WOOD_ITEMS);
    case 'home-detail-zoom': {
      const state = resultState(stateId, options, 4, {
        imagePath: MOCK_UPLOAD_IMAGE,
        resultCount: 10,
        searchBoxVisible: false,
        imagePanelMode: 'full',
        controlsVisible: false
      }, AMALFI_ITEMS);
      return Object.assign(state, {
        detailVisible: true,
        selectedIndex: 1,
        selectedItem: Object.assign({}, state.results[1], {
          pattern_id: '14-57204-002',
          idText: '14-57204-002',
          code: '14-57204-002',
          imageSrc: '/assets/visual-mock/amalfi-002-clean.jpg'
        }),
        detailCountText: '2/10'
      });
    }
    case 'home-results-six':
      return resultState(stateId, options, 6, {
        query: '',
        imagePath: MOCK_UPLOAD_IMAGE,
        resultCount: 10,
        searchBoxVisible: false,
        imagePanelMode: 'strip',
        controlsVisible: false
      }, MIXED_ITEMS);
    case 'home-feedback-negative':
      return resultState(stateId, options, 4, {
        resultCount: 10,
        imagePath: MOCK_UPLOAD_IMAGE,
        searchBoxVisible: false,
        imagePanelMode: 'strip',
        controlsVisible: false,
        feedbackVisible: false,
        feedbackDialogVisible: true,
        feedbackRating: 0,
        feedbackDontRemind: false,
        feedbackCorrectPatternId: '',
        feedbackNote: ''
      });
    case 'home-feedback-positive':
      return resultState(stateId, options, 4, {
        resultCount: 10,
        imagePath: MOCK_UPLOAD_IMAGE,
        searchBoxVisible: false,
        imagePanelMode: 'strip',
        controlsVisible: false,
        feedbackVisible: false,
        feedbackSubmitted: false,
        feedbackDialogVisible: true,
        feedbackRating: 4,
        feedbackDontRemind: false
      });
    default:
      return null;
  }
}

function mineState(stateId, options) {
  const config = options.config;
  const favorites = format(options.formatItems, takeItems(4, WOOD_ITEMS)).map((item) => {
    return Object.assign({}, item, { favorited: true });
  });
  const history = format(options.formatItems, takeItems(6, MIXED_ITEMS));

  if (stateId !== 'mine-favorites' && stateId !== 'mine-history') return null;

  return Object.assign(baseVisualState(stateId), {
    user: {
      username: '我的名字',
      role: config.USER_ROLES.visitor
    },
    displayName: '我的名字',
    roleLabel: '',
    roleLabelVisible: false,
    authEntryVisible: false,
    isVisitor: false,
    authVisible: false,
    activeTab: stateId === 'mine-history' ? config.MINE_TABS.history : config.MINE_TABS.favorites,
    favorites,
    history,
    detailVisible: false,
    selectedItem: null,
    selectedIndex: 0,
    detailTotal: stateId === 'mine-history' ? history.length : favorites.length,
    detailCountText: config.UI_TEXT.emptyDetailCount,
    leadVisible: false
  });
}

function stateFor(rawStateId, options) {
  const stateId = normalizeStateId(rawStateId);
  return homeState(stateId, options) || mineState(stateId, options);
}

module.exports = {
  MOCK_ITEMS,
  AMALFI_ITEMS,
  WOOD_ITEMS,
  MIXED_ITEMS,
  MOCK_UPLOAD_IMAGE,
  stateFor
};
