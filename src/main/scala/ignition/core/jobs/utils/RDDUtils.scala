package ignition.core.jobs.utils

import scala.reflect._
import org.apache.spark.rdd.{PairRDDFunctions, CoGroupedRDD, RDD}
import org.apache.spark.SparkContext._
import org.apache.spark.Partitioner
import org.apache.spark
import org.joda.time.DateTime
import org.joda.time.format.DateTimeFormat

import scalaz.{Success, Validation}

object RDDUtils {
  //TODO: try to make it work for any collection
  implicit class OptionRDDImprovements[V: ClassTag](rdd: RDD[Option[V]]) {
    def flatten: RDD[V] = {
      rdd.flatMap(x => x)
    }
  }

  implicit class SeqRDDImprovements[V: ClassTag](rdd: RDD[Seq[V]]) {
    def flatten: RDD[V] = {
      rdd.flatMap(x => x)
    }
  }

  implicit class ValidatedRDDImprovements[A: ClassTag, B: ClassTag](rdd: RDD[Validation[A, B]]) {

    def mapSuccess(f: B => Validation[A, B]): RDD[Validation[A, B]] = {
      rdd.map({
        case Success(v) => f(v)
        case failure => failure
      })
    }
  }

  implicit class ValidatedPairRDDImprovements[A: ClassTag, B: ClassTag, K: ClassTag](rdd: RDD[(K, Validation[A, B])]) {

    def mapValuesSuccess(f: B => Validation[A, B]): RDD[(K, Validation[A, B])] = {
      rdd.mapValues({
        case Success(v) => f(v)
        case failure => failure
      })
    }
  }

  implicit class RDDImprovements[V: ClassTag](rdd: RDD[V]) {
    def incrementCounter(acc: spark.Accumulator[Int]): RDD[V] = {
      rdd.map(x => { acc += 1; x })
    }

    def incrementCounterIf(cond: (V) => Boolean, acc: spark.Accumulator[Int]): RDD[V] = {
      rdd.map(x => { if (cond(x)) acc += 1; x })
    }
  }

  implicit class PairRDDImprovements[K: ClassTag, V: ClassTag](rdd: RDD[(K, V)]) {
    def incrementCounter(acc: spark.Accumulator[Int]): RDD[(K, V)] = {
      rdd.mapValues(x => { acc += 1; x })
    }

    def incrementCounterIf(cond: (K, V) => Boolean, acc: spark.Accumulator[Int]): RDD[(K, V)] = {
      rdd.mapPreservingPartitions(x => { if(cond(x._1, x._2)) acc += 1; x._2 })
    }

    def flatMapPreservingPartitions[U: ClassTag](f: ((K, V)) => Seq[U]): RDD[(K, U)] = {
      rdd.mapPartitions[(K, U)](kvs => {
        kvs.flatMap[(K,U)](kv => Stream.continually(kv._1) zip f(kv))
      }, preservesPartitioning = true)
    }

    def mapPreservingPartitions[U: ClassTag](f: ((K, V)) => U): RDD[(K, U)] = {
      rdd.mapPartitions[(K, U)](kvs => {
        kvs.map[(K,U)](kv => (kv._1, f(kv)))
      }, preservesPartitioning = true)
    }
    
  }
}
