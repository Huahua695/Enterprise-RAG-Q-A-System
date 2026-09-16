// 商品展示目录：问答等待期与空会话欢迎页轮换展示的"今日好物"。
// 纯前端营销内容，与知识库数据解耦——更换素材只需改这一个文件
// （图片放 src/assets/products/，在此登记名称/卖点/示例问题即可）。
import brandDSalmon from '../assets/products/brand_d_salmon_adult.jpg'
import brandEIndoorLonghair from '../assets/products/brand_e_indoor_longhair.jpg'
import brandFKittenWet from '../assets/products/brand_f_kitten_wet.jpg'
import freezeDried from '../assets/products/freeze_dried.jpg'
import hairballPaste from '../assets/products/hairball_paste.jpg'
import teethingStick from '../assets/products/teething_stick.jpg'
import fishOilJoint from '../assets/products/fish_oil_joint.jpg'

export interface ShowcaseProduct {
  name: string
  tagline: string
  description: string
  image: string
  question: string
}

export const showcaseProducts: ShowcaseProduct[] = [
  {
    name: '品牌D 三文鱼味成猫粮',
    tagline: '深海三文鱼 · 全价成猫干粮',
    description: '精选三文鱼原料，富含优质蛋白与 Omega-3，颗粒大小适合成猫采食，日常营养一瓶搞定。',
    image: brandDSalmon,
    question: '店里都有哪些猫粮可以选？',
  },
  {
    name: '品牌E 室内长毛猫专用粮',
    tagline: '化毛配方 · 室内猫专属',
    description: '针对室内长毛猫设计的化毛配方，帮助排出毛球，照顾它的肠胃与毛发双重需求。',
    image: brandEIndoorLonghair,
    question: '长毛猫总吐毛球，有化毛配方的猫粮推荐吗？',
  },
  {
    name: '品牌F 幼猫湿粮包',
    tagline: '幼猫成长 · 干湿搭配',
    description: '细腻肉质好消化，补水又补营养，与幼猫干粮搭配喂养，陪伴离乳期到成年的每一步。',
    image: brandFKittenWet,
    question: '品牌F幼猫湿粮包怎么和干粮搭配喂？',
  },
  {
    name: '冻干系列 主粮伴侣',
    tagline: '冻干锁鲜 · 复水即鲜粮',
    description: '-40℃ 冻干工艺锁住肉香与营养，直接拌粮或温水复水，挑食猫也难以抗拒。',
    image: freezeDried,
    question: '冻干零食的复水方法和喂食量是多少？',
  },
  {
    name: '化毛膏 营养膏',
    tagline: '软管设计 · 挤出方便',
    description: '温和配方帮助毛球排出，软管包装精准控量，换毛季的贴心小帮手。',
    image: hairballPaste,
    question: '化毛膏的喂食频率是多少？适合什么阶段？',
  },
  {
    name: '磨牙棒 三档硬度',
    tagline: '硬度分级 · 总有一档合适',
    description: '按咬合力度分三档硬度，幼犬成犬各取所需，洁齿又解闷。',
    image: teethingStick,
    question: '磨牙棒的硬度分级分别对应什么犬型？',
  },
  {
    name: '鱼油关节宝',
    tagline: '软胶囊 · 好吸收',
    description: '深海鱼油搭配关节养护成分，软胶囊好喂好吸收，守护它跑跳的每一天。',
    image: fishOilJoint,
    question: '鱼油和关节宝适用于什么症状？用法用量是？',
  },
]
