$(document).ready(function(){
  $('#news-listing .slick-slider').slick({
    dots: true,
    infinite: true,
    autoplay: true,
    speed: 500,
    slidesToShow: 1,
    centerMode: false,
    variableWidth: false,
    adaptiveHeight: true,
    arrows: true
  });
});