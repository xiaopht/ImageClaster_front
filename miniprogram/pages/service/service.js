const config = require('../../config');
const i18n = require('../../utils/i18n');
const api = require('../../utils/api');

const OCCUPATION_OPTIONS = [
  { id: 1, labelKey: 'serviceOccupationDesigner' },
  { id: 2, labelKey: 'serviceOccupationManager' },
  { id: 3, labelKey: 'serviceOccupationDistributor' },
  { id: 4, labelKey: 'serviceOccupationDeveloper' },
  { id: 5, labelKey: 'serviceOccupationStudent' },
  { id: 6, labelKey: 'serviceOccupationOwner' },
  { id: 7, labelKey: 'serviceOccupationBuilder' },
  { id: 8, labelKey: 'serviceOccupationOther' }
];

const REGION_OPTIONS = [
  { id: 1, labelKey: 'serviceRegionEast' },
  { id: 2, labelKey: 'serviceRegionNorth' },
  { id: 3, labelKey: 'serviceRegionSouth' },
  { id: 4, labelKey: 'serviceRegionSouthwest' },
  { id: 5, labelKey: 'serviceRegionOverseas' },
  { id: 6, labelKey: 'serviceRegionOther' }
];

const CONTACT = {
  region: '',
  name: 'Schattdecor Sales',
  phone: '15815811558',
  email: '15815811558@163.com'
};

const STEPS = {
  occupation: 'occupation',
  region: 'region',
  complete: 'complete'
};

let messageSequence = 0;

function message(type, value) {
  messageSequence += 1;
  return {
    id: `service-message-${messageSequence}`,
    type,
    value: value || '',
    textKey: value || ''
  };
}

function openingMessages() {
  return [
    message('assistantText', 'serviceWelcome'),
    message('occupationPrompt')
  ];
}

function regionContact(regionId, language, text) {
  const option = REGION_OPTIONS.find((item) => String(item.id) === String(regionId));
  if (!option) return CONTACT;
  const english = i18n.text('en-US')[option.labelKey];
  const region = language === 'zh-CN' ? `${text[option.labelKey]} ${english}` : text[option.labelKey];
  return Object.assign({}, CONTACT, { region });
}

Page({
  data: {
    brand: config.BRAND,
    language: i18n.DEFAULT_LANGUAGE,
    text: i18n.text(i18n.DEFAULT_LANGUAGE),
    occupationOptions: [],
    regionOptions: [],
    messages: openingMessages(),
    step: STEPS.occupation,
    occupationSelected: '',
    regionSelected: '',
    contact: CONTACT,
    leadSubmitted: false,
    inputValue: '',
    canSend: false,
    scrollTop: 0,
    visualState: ''
  },

  onLoad(options) {
    this.visualState = options && options.visualState;
  },

  onShow() {
    this.applyLanguage();
    if (this.visualState) {
      this.applyVisualState(this.visualState);
      this.visualState = '';
    }
  },

  applyLanguage() {
    const language = i18n.currentLanguage();
    const text = i18n.text(language);
    this.setData({
      language,
      text,
      occupationOptions: OCCUPATION_OPTIONS.map((item) => ({ id: item.id, label: text[item.labelKey] })),
      regionOptions: REGION_OPTIONS.map((item) => ({ id: item.id, label: text[item.labelKey] })),
      contact: regionContact(this.data.regionSelected, language, text)
    });
    wx.setNavigationBarTitle({ title: text.servicePageTitle });
    i18n.applyTabBar(language);
  },

  applyVisualState(visualState) {
    if (visualState === 'service-chat-long' || visualState === 'customer-service-long') {
      this.setData({
        visualState,
        messages: openingMessages()
          .concat(message('user', '1'), message('regionPrompt'), message('user', '4'), message('contact')),
        step: STEPS.complete,
        occupationSelected: '1',
        regionSelected: '4',
        contact: regionContact('4', this.data.language, this.data.text),
        leadSubmitted: true,
        scrollTop: 1600
      });
      return true;
    }
    if (visualState === 'service-chat-short' || visualState === 'customer-service-short') {
      this.setData({
        visualState,
        messages: openingMessages().concat(message('user', '1'), message('regionPrompt')),
        step: STEPS.region,
        occupationSelected: '1',
        regionSelected: '',
        contact: CONTACT,
        leadSubmitted: false,
        scrollTop: 680
      });
      return true;
    }
    return false;
  },

  chooseOccupation(e) {
    this.submitReply(String(e.currentTarget.dataset.id || ''));
  },

  chooseRegion(e) {
    this.submitReply(String(e.currentTarget.dataset.id || ''));
  },

  handleInput(e) {
    const inputValue = String(e.detail.value || '').trim();
    this.setData({
      inputValue,
      canSend: inputValue.length > 0
    });
  },

  sendMessage() {
    const reply = String(this.data.inputValue || '').trim();
    if (!reply) return;
    this.setData({ inputValue: '', canSend: false });
    this.submitReply(reply);
  },

  submitReply(reply) {
    if (this.data.step === STEPS.complete) {
      if (reply === '0') {
        this.restartConversation(reply);
        return;
      }
      this.appendMessages([message('user', reply), message('assistantText', 'serviceCompleteHint')]);
      return;
    }
    if (this.data.step === STEPS.occupation) {
      if (!/^[1-8]$/.test(reply)) {
        this.appendMessages([message('user', reply), message('assistantText', 'serviceOccupationInvalid')]);
        return;
      }
      this.setData({
        occupationSelected: reply,
        step: STEPS.region
      });
      this.appendMessages([message('user', reply), message('regionPrompt')]);
      return;
    }
    if (!/^[1-6]$/.test(reply)) {
      this.appendMessages([message('user', reply), message('assistantText', 'serviceRegionInvalid')]);
      return;
    }
    this.setData({
      regionSelected: reply,
      contact: regionContact(reply, this.data.language, this.data.text),
      step: STEPS.complete,
      leadSubmitted: false
    });
    this.appendMessages([message('user', reply), message('contact')]);
    this.submitServiceLead();
  },

  restartConversation(reply) {
    this.setData({
      messages: [message('user', reply), message('assistantText', 'serviceRestarted'), message('occupationPrompt')],
      step: STEPS.occupation,
      occupationSelected: '',
      regionSelected: '',
      contact: CONTACT,
      leadSubmitted: false,
      scrollTop: this.data.scrollTop + 1200
    });
  },

  optionLabel(options, id) {
    const option = options.find((item) => String(item.id) === String(id));
    return option ? option.label : '';
  },

  plainMessages() {
    return (this.data.messages || []).map((item) => ({
      type: item.type,
      value: item.value || '',
      text_key: item.textKey || ''
    }));
  },

  submitServiceLead() {
    if (this.data.leadSubmitted || !this.data.occupationSelected || !this.data.regionSelected) return;
    const payload = {
      profession_id: String(this.data.occupationSelected),
      profession_label: this.optionLabel(this.data.occupationOptions, this.data.occupationSelected),
      region_id: String(this.data.regionSelected),
      region_label: this.optionLabel(this.data.regionOptions, this.data.regionSelected),
      contact: this.data.contact,
      messages: this.plainMessages(),
      language: this.data.language,
      source: 'service_chat'
    };
    this.setData({ leadSubmitted: true });
    api.submitServiceLead(payload).catch(() => {
      this.setData({ leadSubmitted: false });
    });
  },

  appendMessages(newMessages) {
    this.setData({
      messages: this.data.messages.concat(newMessages),
      scrollTop: this.data.scrollTop + 1200
    });
  },

  copyContact(e) {
    const type = e.currentTarget.dataset.type;
    const labels = this.data.text;
    const text = type === 'phone'
      ? CONTACT.phone
      : `${labels.serviceContactRegion}: ${this.data.contact.region}\n${labels.serviceContactName}: ${CONTACT.name}\n${labels.serviceContactPhone}: ${CONTACT.phone}\n${labels.serviceContactEmail}: ${CONTACT.email}`;
    wx.setClipboardData({
      data: text,
      success: () => {
        wx.showToast({ title: this.data.text.copied, icon: config.TOAST_ICONS.none });
      }
    });
  },

  goHome() {
    wx.switchTab({ url: config.ROUTES.index });
  },

  goCamera() {
    wx.switchTab({ url: config.ROUTES.camera });
  },

  goMine() {
    wx.switchTab({ url: config.ROUTES.mine });
  }
});
