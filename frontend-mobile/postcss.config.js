export default {
  plugins: {
    'postcss-px-to-viewport-8-plugin': {
      viewportWidth: 375,
      unitPrecision: 5,
      minPixelValue: 2,
      propList: ['*'],
      selectorBlackList: ['.ignore-'],
    },
  },
}
