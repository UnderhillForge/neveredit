# -*- coding: ISO-8859-1 -*-
"""Resource select_icon_sel_png (from file select_icon_sel.png)"""
# written by resourcepackage: (1, 0, 0)
source = 'select_icon_sel.png'
package = 'neveredit.resources.images'

### wxPython specific functions
originalExtension = '.png'
import wx
import io
def getData( ):
	"""Return the data from the resource as a simple string"""
	return data
def getImage( ):
	"""Return the data from the resource as a wxImage"""
	stream = io.BytesIO(data.encode('latin1'))
	return wx.Image(stream)
def getBitmap( ):
	"""Return the data from the resource as a wxBitmap"""
	return wx.Bitmap(getImage())
def getIcon( ):
	"""Return the data from the resource as a wxIcon"""
	icon = wx.Icon()
	icon.CopyFromBitmap(getBitmap())
	return icon
data = "‰PNG\015\012\032\012\000\000\000\015IHDR\000\000\000\032\000\000\000\030\010\002\000\000\000kàz’\000\000\000\003sBIT\010\010\010ÛáOà\000\000\004ÓIDAT8u•\
Ï\\G\021Ç¿UÝýÞ¼™YÏŒ=»³Þ\004Ûñ’`@¹á¿Á2‘ÌÅøˆŒ\021p@ð_ ¡ü\003 GAÑ\012$®\\àf$Ä\001\020\
H!àµMb“ØÁØŽãõÌ¼yïu¿îª\034ÞzXñ£o¥®þÔ·Ôõƒööö¬µøÿG\011””ŒU\011D¤`R\026Ž¤¬ªÌ\
¬ªç|>·MÓÌf3\000€\020\031U\005˜T” P\"¢Î™ISÎÌ\"Â \000\002=4_\020ïß¿o×l%†ªvž\000\000\"b\001€\004J)\
‘MŸö—Ëaóduð•ù\027\031¤ªD´&\000°àC›„\023%V\"ˆ\020«*\011<´\032TóUÙ_Vvåb=jÃ¯ã{¯W/gù€\
™×8\"\002`\001t¶¢\005\000EBZöbÙ_•ÃÅª¨rñ\022æÇêå–¯«¶&aÖÅ¾<x=½Ú!Ö„C\\Œ‘ˆž¹¥\016Ò|ä\
Ë¢t¦±ñyÑ.f«àC\031ÛÄ‘Ë$\024ÅÇðJvì¶ÜyÍŸbæN×\032Çª©Eœ·Ë½éÏ\037ÎnºÞ_¾nž®ö·V\
\037\027õÁþ\037\036ÅJÄ“÷>y©Bl\033œ\011ƒ[Å\0071´A’ª\036&‹\010M\0140E\021ŸîÿéQüøæ‰0÷ÍÊ‡\024}ŒUüÕ\037\
ßywÙ4¾i\021š$MlÛÔ¯ñ´X”mEITU5i’ \031±eUm}ôesÚïÜ|þ,„ÐFM>ÔAË2’Êwž~ðn\
\035ê\030ÚÔ\006•\006a±x%õ÷Ýû¡ñˆ©H*H1©°\022©ªÄ4«¶î®\026m€„\024[ø2”K¯$×¯ÿä÷¿8øð¯«¶\
\011>¤:†6ê©fã®û0Ä\0245’¶I\005\022\014”‰H\011`Ú;¯\027ËE\010^CH1´MåIíÎÎÎ\017ßüÑ\037Y~tËGÏ\
Ré³ç‹çÿx|«¼Û¦&\011+,„D’;l/fî™|kuüÎÁÁ—F'¢hhR½b%±l>ÿÚîw¾ýÍëo½\025Ï=\
y¢Oë\025fnöåWÏµ§%æÍaµÁB“\005@\012cL–õ>W½t«úèìp˜‚†6Æº5\012\030›R»»»{í[ßýéÛoŸ\
Û>¹;;³1\032\037ïU\023¢Š%ˆ\002\001\020f@\011Jp.?\023N>lÂƒ‡«ßÞþçÏ~÷þ;¿y/²HjÕ§b0:9;qíÚ\
7–ç!úcÇúý~Ï8›\010ˆÂ0\002\"eKŠ”’#g\014½¬/}òçÕÞ£¿mêtÓ:çúÿÒOB\010Mlðýï­Ëu\
ÿötºµ½½ãŒ\005TDÚnLØD0L`±ÖöóÞ×7¾ª”\010¦\025­ôàÓ\020ÂÕ«W‰HD.]º4ŸÏ'“Éd2\
qÎu]±®dUµ\000DDU-;74ÛÍ¶Ïƒj\"Ã¾\016\002½råÊÙ³gïÝ»ÇÌUUåyže\031\021uý\024\007€\001@\022AÈÑ\
 ·1ž\036ßšnžœîLÇÓñxL”ÎŸ??\032.^¼(\"7nÜ\030\016‡EQ8çºÜJ\003`Y\016{Î(z”Q¡ÔcfŽm\
HßxãkÞ×)¥²,»÷\033\033\033Î9cŒªŠÈz4½PÇ$ÐDJ¬0p.w¶°Ö²ë\025y6\030\016'“Éx<\036\016‡—/_\006°\
··×ÕéÑé´ÖhIÑé\013€e…\010\023‰*3gÎ\031c€\"ÆhŒY.—Ýr\010!Xkÿç†±ÚÅ\020e°\010È˜¤\0020«Àf\006\000\
`Œ\021\021ïý…\013\027œs)¥î÷ÖêÖJ-)F£Ñ¿÷Ö‹»£CQU½÷EQÔuÍÌÃáp0\0308çŽ‚ˆh>ŸÛ~¿_\024Å\
Ëþ“çyžç!\004\"Ê²,Ë2fîvØ:ðææægŠ;G%\0076Ž²\000\000\000\000IEND®B`‚"
### end
