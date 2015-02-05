package ignition.core.utils
import scala.collection.IterableLike
import scala.collection.generic.CanBuildFrom
import scala.language.implicitConversions
import scalaz._

object CollectionUtils {

  //TODO: review this code
  class RichCollection[A, Repr](xs: IterableLike[A, Repr]){
    def distinctBy[B, That](f: A => B)(implicit cbf: CanBuildFrom[Repr, A, That]) = {
      val builder = cbf(xs.repr)
      val i = xs.iterator
      var set = Set[B]()
      while(i.hasNext) {
        val o = i.next
        val b = f(o)
        if (!set(b)) {
          set += b
          builder += o
        }
      }
      builder.result
    }
  }

  implicit def toRich[A, Repr](xs: IterableLike[A, Repr]) = new RichCollection(xs)

  // TODO: implement just one for all type
  implicit class ValidatedSetCollection[A, B](seq: Set[Validation[A, B]]) {

    def mapSuccess(f: B => Validation[A, B]): Set[Validation[A, B]] = {
      seq.map({
        case Success(v) => f(v)
        case failure => failure
      })
    }
  }

  implicit class ValidatedListCollection[A, B](seq: List[Validation[A, B]]) {
    def mapSuccess(f: B => Validation[A, B]): List[Validation[A, B]] = {
      seq.map({
        case Success(v) => f(v)
        case failure => failure
      })
    }
  }

  implicit class ValidatedSeqCollection[A, B](seq: Seq[Validation[A, B]]) {
    def mapSuccess(f: B => Validation[A, B]): Seq[Validation[A, B]] = {
      seq.map({
        case Success(v) => f(v)
        case failure => failure
      })
    }
  }

  implicit class ValidatedIterableCollection[A, B](seq: Iterable[Validation[A, B]]) {

    def mapSuccess(f: B => Validation[A, B]): Iterable[Validation[A, B]] = {
      seq.map({
        case Success(v) => f(v)
        case failure => failure
      })
    }
  }

  implicit class OptionCollection(opt: Option[String]) {
    def isBlank: Boolean = {
      opt.isEmpty || opt.get.trim.isEmpty
    }

    def nonBlank: Boolean = !opt.isBlank

    def noneIfBlank: Option[String] = {
      if (opt.isBlank) None else opt
    }

  }

  // Useful to be called from java code
  def mutableMapToImmutable[K, V](map: scala.collection.mutable.Map[K, V]): Map[K, V] = {
    map.toMap
  }
}
